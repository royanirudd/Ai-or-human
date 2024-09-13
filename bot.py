import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient
import random
from datetime import datetime, timedelta


# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')

# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Connect to MongoDB
client = MongoClient(MONGODB_URI)
db = client['ai_or_human_game']
users_collection = db['users']
prompts_collection = db['prompts']

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')


async def get_or_create_user(user_id, username):
    user = users_collection.find_one({"user_id": str(user_id)})
    if not user:
        user = {
            "user_id": str(user_id),
            "username": username,
            "points": 0,
            "daily_guesses": 0,
            "last_guess_date": datetime.utcnow()
        }
        users_collection.insert_one(user)
    return user

# Command to play the guessing game
@bot.command()
async def play(ctx):
    user = await get_or_create_user(ctx.author.id, ctx.author.name)
    
    # Check if the user has reached their daily limit
    today = datetime.utcnow().date()
    if user['last_guess_date'].date() < today:
        user['daily_guesses'] = 0
    
    if user['daily_guesses'] >= 5:
        await ctx.send("You've reached your daily limit of 5 guesses. Try again tomorrow!")
        return

    # Get a random prompt
    prompt = prompts_collection.aggregate([{ "$sample": { "size": 1 } }]).next()
    
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
                 "$set": {"last_guess_date": datetime.utcnow()}}
            )
            await ctx.send("Correct! You earned 1 point.")
        else:
            users_collection.update_one(
                {"user_id": str(ctx.author.id)},
                {"$inc": {"daily_guesses": 1},
                 "$set": {"last_guess_date": datetime.utcnow()}}
            )
            await ctx.send("Sorry, that's incorrect. No points earned.")

# Command to check user's points
@bot.command()
async def points(ctx):
    user = await get_or_create_user(ctx.author.id, ctx.author.name)
    await ctx.send(f"You have {user['points']} points.")

# Command to submit a new prompt
@bot.command()
async def submit(ctx, *, prompt):
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


# Run the bot
bot.run(DISCORD_TOKEN)
