import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import pymongo
from datetime import datetime, timezone
import asyncio
import random
import traceback

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')

# Set up MongoDB connection
client = pymongo.MongoClient(MONGODB_URI)
db = client['ai_or_human_game']
users_collection = db['users']
prompts_collection = db['prompts']

# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='ai!', intents=intents)

# Remove the default help command
bot.remove_command('help')

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command()
async def ping(ctx):
    """A simple command to check if the bot is responsive."""
    await ctx.send('Pong!')

# Helper function to get or create a user
async def get_or_create_user(user_id, username):
    user = users_collection.find_one({"user_id": str(user_id)})
    if not user:
        user = {
            "user_id": str(user_id),
            "username": username,
            "points": 0,
            "daily_guesses": 0,
            "last_guess_date": datetime.now(timezone.utc)
        }
        users_collection.insert_one(user)
    return user

@bot.command()
async def play(ctx):
    """Starts the AI or Human guessing game. You'll be presented with a prompt and need to guess if it was written by an AI or a human."""
    user = await get_or_create_user(ctx.author.id, ctx.author.name)
    
    # Check if the user has reached their daily limit
    today = datetime.now(timezone.utc).date()
    if user['last_guess_date'].date() < today:
        user['daily_guesses'] = 0
    
    if user['daily_guesses'] >= 5:
        await ctx.send("You've reached your daily limit of 5 guesses. Try again tomorrow!")
        return

    # Get a random prompt
    try:
        prompt = prompts_collection.aggregate([{ "$sample": { "size": 1 } }]).next()
    except StopIteration:
        await ctx.send("Sorry, there are no prompts available. Please add some prompts using the !submit command.")
        return

    await ctx.send(f"Prompt: {prompt['prompt']}\n\nAnswer: {prompt['answer']}\n\nIs this answer from AI or Human? Reply with 'AI' or 'Human'.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['ai', 'human']

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Sorry, you didn't reply in time!")
    else:
        is_correct = (msg.content.lower() == 'ai') == prompt['is_ai']
        if is_correct:
            users_collection.update_one(
                {"user_id": str(ctx.author.id)},
                {"$inc": {"points": 1, "daily_guesses": 1},
                 "$set": {"last_guess_date": datetime.now(timezone.utc)}}
            )
            await ctx.send("Correct! You earned 1 point.")
        else:
            users_collection.update_one(
                {"user_id": str(ctx.author.id)},
                {"$inc": {"daily_guesses": 1},
                 "$set": {"last_guess_date": datetime.now(timezone.utc)}}
            )
            await ctx.send("Sorry, that's incorrect. No points earned.")

@bot.command()
async def points(ctx):
    """Checks your current point total. You earn points for correct guesses in the game."""
    user = await get_or_create_user(ctx.author.id, ctx.author.name)
    await ctx.send(f"You have {user['points']} points.")

@bot.command()
async def submit(ctx, *, prompt):
    """Allows you to submit a new prompt and answer for the game. Your submission will be reviewed before being added to the game."""
    await ctx.send("Please provide a 3-4 sentence answer to your prompt.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=300.0)
    except asyncio.TimeoutError:
        await ctx.send("Sorry, you didn't reply in time!")
    else:
        new_prompt = {
            "prompt": prompt,
            "answer": msg.content,
            "is_ai": False,
            "created_by": str(ctx.author.id)
        }
        prompts_collection.insert_one(new_prompt)
        await ctx.send("Your prompt and answer have been submitted. If it fools other players, you'll earn 3 points!")

@bot.command()
@commands.is_owner()
async def addprompt(ctx, *, content):
    """(Bot Owner Only) Allows manual addition of prompts to the database."""
    try:
        prompt, answer, is_ai = content.split('|')
        new_prompt = {
            "prompt": prompt.strip(),
            "answer": answer.strip(),
            "is_ai": is_ai.strip().lower() == 'true',
            "created_by": None
        }
        prompts_collection.insert_one(new_prompt)
        await ctx.send("Prompt added successfully!")
    except ValueError:
        await ctx.send("Invalid format. Use: !addprompt prompt | answer | is_ai")

@bot.command(name='help')
async def help_command(ctx):
    """Shows this help message with explanations of all available commands."""
    help_embed = discord.Embed(title="AI or Human Bot Help", 
                               description="Here are the available commands:", 
                               color=discord.Color.blue())

    for command in bot.commands:
        if command.hidden:
            continue
        name = f"`ai!{command.name}`"
        value = command.help or "No description available."
        # Truncate the value if it's too long
        if len(value) > 1024:
            value = value[:1021] + "..."
        help_embed.add_field(name=name, value=value, inline=False)

    await ctx.send(embed=help_embed)

# Run the bot
try:
    bot.run(DISCORD_TOKEN)
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
