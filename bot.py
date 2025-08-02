"""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

import asyncio
import json
import logging
import os
import platform
import random
import sys
import re

from logging.handlers import RotatingFileHandler

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Bot, Context
from helpers.message_handler import process_message, register_message_handler

import exceptions

if not os.path.isfile(f"{os.path.realpath(os.path.dirname(__file__))}/config/config.json"):
    sys.exit("'config.json' not found! Please add it and try again.")
else:
    with open(f"{os.path.realpath(os.path.dirname(__file__))}/config/config.json") as file:
        config = json.load(file)

"""
Setup bot intents (events restrictions)
For more information about intents, please go to the following websites:
https://discordpy.readthedocs.io/en/latest/intents.html
https://discordpy.readthedocs.io/en/latest/intents.html#privileged-intents


Default Intents:
intents.bans = True
intents.dm_messages = True
intents.dm_reactions = True
intents.dm_typing = True
intents.emojis = True
intents.emojis_and_stickers = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_scheduled_events = True
intents.guild_typing = True
intents.guilds = True
intents.integrations = True
intents.invites = True
intents.messages = True # `message_content` is required to get the content of the messages
intents.reactions = True
intents.typing = True
intents.voice_states = True
intents.webhooks = True

Privileged Intents (Needs to be enabled on developer portal of Discord), please use them only if you need them:
intents.members = True
intents.message_content = True
intents.presences = True
"""

intents = discord.Intents.default()

"""
Uncomment this if you want to use prefix (normal) commands.
It is recommended to use slash commands and therefore not use prefix commands.

If you want to use prefix commands, make sure to also enable the intent below in the Discord developer portal.
"""
intents.message_content = True

bot = Bot(
    command_prefix=commands.when_mentioned_or(config["prefix"]),
    intents=intents,
    help_command=None,
)

# Setup both of the loggers


class LoggingFormatter(logging.Formatter):
    # Colors
    black = "\x1b[30m"
    red = "\x1b[31m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    blue = "\x1b[34m"
    gray = "\x1b[38m"
    # Styles
    reset = "\x1b[0m"
    bold = "\x1b[1m"

    COLORS = {
        logging.DEBUG: gray + bold,
        logging.INFO: blue + bold,
        logging.WARNING: yellow + bold,
        logging.ERROR: red,
        logging.CRITICAL: red + bold,
    }

    def format(self, record):
        log_color = self.COLORS[record.levelno]
        format = "(black){asctime}(reset) (levelcolor){levelname:<8}(reset) (green){name}(reset) {message}"
        format = format.replace("(black)", self.black + self.bold)
        format = format.replace("(reset)", self.reset)
        format = format.replace("(levelcolor)", log_color)
        format = format.replace("(green)", self.green + self.bold)
        formatter = logging.Formatter(format, "%Y-%m-%d %H:%M:%S", style="{")
        return formatter.format(record)

# Create a formatter for file handlers.
file_handler_formatter = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
)

# Create the main logger and set its level to DEBUG so all messages are processed.
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)

# Console handler (only logs INFO and above)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(LoggingFormatter())

# Rotating file handler for normal (INFO and above) messages.
file_handler = RotatingFileHandler(
    filename="discord.log",
    encoding="utf-8",
    mode="w",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(file_handler_formatter)

# Custom rotating file handler for DEBUG messages.
debug_file_handler = RotatingFileHandler(
    filename="discord_debug.log",
    encoding="utf-8",
    mode="w",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
)
debug_file_handler.setLevel(logging.DEBUG)
debug_file_handler.setFormatter(file_handler_formatter)

# Add all handlers to the logger.
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.addHandler(debug_file_handler)

# Attach the logger to the bot.
bot.logger = logger

#updating version

async def init_db():
    async with aiosqlite.connect(
        f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
    ) as db:
        with open(
            f"{os.path.realpath(os.path.dirname(__file__))}/database/schema.sql"
        ) as file:
            await db.executescript(file.read())
        await db.commit()


"""
Create a bot variable to access the config file in cogs so that you don't need to import it every time.

The config is available using the following code:
- bot.config # In this file
- self.bot.config # In cogs
"""
bot.config = config


@bot.event
async def on_ready() -> None:
    """
    The code in this event is executed when the bot is ready.
    """
    bot.logger.info(f"Logged in as {bot.user.name}")
    bot.logger.info(f"discord.py API version: {discord.__version__}")
    bot.logger.info(f"Python version: {platform.python_version()}")
    bot.logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
    bot.logger.info("-------------------")
    status_task.start()
    if config["sync_commands_globally"]:
        bot.logger.info("Syncing commands globally...")
        await bot.tree.sync()



def channel_member_count(channel: discord.VoiceChannel, count_bots=False) -> int:
    return len([member for member in channel.members if not member.bot or count_bots])


@bot.event
async def on_voice_state_update(member, before, after) -> None:
    if member.bot:
        return
    # If bot is already in a voice channel on that guild
    if member.guild.voice_client:
        # If the bot is alone in the voice channel, disconnect
        if channel_member_count(member.guild.voice_client.channel) == 0:
            logger.info(
                f"Disconnected from {member.guild.voice_client.channel} because I was alone in it."
            )
            await member.guild.voice_client.disconnect()

            return
    else:
        # If someone joins a voice channel, join it
        if after.channel:
            await after.channel.connect()
            logger.info(f"Connected to {after.channel} because someone joined it.")
            return


@tasks.loop(minutes=1.0)
async def status_task() -> None:
    """
    Setup the game status task of the bot.
    """
    statuses = ["sex update"]
    await bot.change_presence(activity=discord.Game(random.choice(statuses)))


@bot.event
async def on_message(message: discord.Message) -> None:
    # Ignore bots (including self)
    if message.author == bot.user or message.author.bot:
        return

    # Dispatch to registered handlers
    await process_message(message)

    # Ensure commands still work
    await bot.process_commands(message)


@bot.event
async def on_command_completion(context: Context) -> None:
    """
    The code in this event is executed every time a normal command has been *successfully* executed.

    :param context: The context of the command that has been executed.
    """
    full_command_name = context.command.qualified_name
    split = full_command_name.split(" ")
    executed_command = str(split[0])
    parameters = str(split[1:])
    if context.guild is not None:
        bot.logger.info(
            f"Executed {executed_command} command in {context.guild.name} (ID: {context.guild.id}) by {context.author} (ID: {context.author.id})"
        )
    else:
        bot.logger.info(
            f"Executed {executed_command} command by {context.author} (ID: {context.author.id}) in DMs"
        )


@bot.event
async def on_command_error(context: Context, error) -> None:
    """
    The code in this event is executed every time a normal valid command catches an error.

    :param context: The context of the normal command that failed executing.
    :param error: The error that has been faced.
    """
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        embed = discord.Embed(
            description=f"**Please slow down** - You can use this command again in {f'{round(hours)} hours' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} seconds' if round(seconds) > 0 else ''}.",
            color=0xE02B2B,
        )
        await context.send(embed=embed)
    elif isinstance(error, exceptions.UserBlacklisted):
        """
        The code here will only execute if the error is an instance of 'UserBlacklisted', which can occur when using
        the @checks.not_blacklisted() check in your command, or you can raise the error by yourself.
        """
        embed = discord.Embed(
            description="You are blacklisted from using the bot!", color=0xE02B2B
        )
        await context.send(embed=embed)
        if context.guild:
            bot.logger.warning(
                f"{context.author} (ID: {context.author.id}) tried to execute a command in the guild {context.guild.name} (ID: {context.guild.id}), but the user is blacklisted from using the bot."
            )
        else:
            bot.logger.warning(
                f"{context.author} (ID: {context.author.id}) tried to execute a command in the bot's DMs, but the user is blacklisted from using the bot."
            )
    elif isinstance(error, exceptions.UserNotOwner):
        """
        Same as above, just for the @checks.is_owner() check.
        """
        embed = discord.Embed(
            description="You are not the owner of the bot!", color=0xE02B2B
        )
        await context.send(embed=embed)
        if context.guild:
            bot.logger.warning(
                f"{context.author} (ID: {context.author.id}) tried to execute an owner only command in the guild {context.guild.name} (ID: {context.guild.id}), but the user is not an owner of the bot."
            )
        else:
            bot.logger.warning(
                f"{context.author} (ID: {context.author.id}) tried to execute an owner only command in the bot's DMs, but the user is not an owner of the bot."
            )
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            description="You are missing the permission(s) `"
            + ", ".join(error.missing_permissions)
            + "` to execute this command!",
            color=0xE02B2B,
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            description="I am missing the permission(s) `"
            + ", ".join(error.missing_permissions)
            + "` to fully perform this command!",
            color=0xE02B2B,
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="Error!",
            # We need to capitalize because the command arguments have no
            # capital letter in the code.
            description=str(error).capitalize(),
            color=0xE02B2B,
        )
        await context.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        await context.send(
            f"Command {context.invoked_with} not found. Type `/help` for a list of commands."
        )
    else:
        raise error


async def load_cogs() -> None:
    """
    The code in this function is executed whenever the bot will start.
    """
    for file in os.listdir(f"{os.path.realpath(os.path.dirname(__file__))}/cogs"):
        if file.endswith(".py"):
            extension = file[:-3]
            try:
                await bot.load_extension(f"cogs.{extension}")
                bot.logger.info(f"Loaded extension '{extension}'")
            except Exception as e:
                exception = f"{type(e).__name__}: {e}"
                bot.logger.error(f"Failed to load extension {extension}\n{exception}")
                
# User lists for different thinkso behaviors
THINKSO_OPPOSITE_USERS = [157694052337188865]  # Responds with opposite emoji
THINKSO_FOLLOW_USERS = [66660999314280448]     # Responds with same emoji

@register_message_handler(user_ids=THINKSO_OPPOSITE_USERS + THINKSO_FOLLOW_USERS)
async def idontthinkso(message: discord.Message) -> None:
    import re
    
    emojis = await bot.fetch_application_emojis()
    # [<Emoji id=1399554109014675507 name='NOIDONTTHINKSO' animated=True managed=False>, <Emoji id=1399554124390858852 name='YESIDOTHINKSO' animated=True managed=False>]
    # If the message is only one of the emojis, respond with the other one
    # Check if the message is only a single emoji (It looks like <a:NOIDONTTHINKSO:803763692210487357>)
    
    # Regex to match a single emoji in the message (animated or static)
    emoji_pattern = r'^<a?:([^:]+):\d+>$'
    match = re.match(emoji_pattern, message.content.strip())
    
    if match:
        emoji_name = match.group(1).lower()  # Get emoji name in lowercase
        
        # Check if it's one of our target emojis
        if emoji_name in ['noidontthinkso', 'yesidothinkso']:
            # Determine user behavior
            if message.author.id in THINKSO_OPPOSITE_USERS:
                # Opposite behavior - respond with the opposite emoji
                if emoji_name == 'noidontthinkso':
                    target_emoji = discord.utils.get(emojis, name='YESIDOTHINKSO')
                else:  # yesidothinkso
                    target_emoji = discord.utils.get(emojis, name='NOIDONTTHINKSO')
            elif message.author.id in THINKSO_FOLLOW_USERS:
                # Follow behavior - respond with the same emoji
                target_emoji = discord.utils.get(emojis, name=emoji_name.upper())
            else:
                # Default to opposite behavior for unknown users
                if emoji_name == 'noidontthinkso':
                    target_emoji = discord.utils.get(emojis, name='YESIDOTHINKSO')
                else:  # yesidothinkso
                    target_emoji = discord.utils.get(emojis, name='NOIDONTTHINKSO')
            
            if target_emoji:
                await message.channel.send(str(target_emoji))


def find_thinkso(content: str):
    """
    Find a thinkso emoji in the message content.
    Returns the emoji name in uppercase if found, False otherwise.
    """
    # Regex to match emoji patterns (both animated and static)
    emoji_pattern = r'<a?:([^:]+):\d+>'
    matches = re.findall(emoji_pattern, content)
    
    for match in matches:
        emoji_name = match.upper()
        if emoji_name in ['NOIDONTTHINKSO', 'YESIDOTHINKSO']:
            return emoji_name
    
    return False

def get_opposite_thinkso(thinkso: str):
    """
    Given a thinkso emoji name, return the opposite one.
    """
    if thinkso == 'NOIDONTTHINKSO':
        return 'YESIDOTHINKSO'
    elif thinkso == 'YESIDOTHINKSO':
        return 'NOIDONTTHINKSO'
    else:
        raise ValueError(f"Invalid thinkso: {thinkso}")

async def check_thinkso_pair(channel: discord.TextChannel, message_id: int, trigger_user: discord.User = None) -> None:
    """
    Check for thinkso pairs around a message and fix if manipulation is detected.
    """
    try:
        # Get messages around the target message (2 above, 2 below)
        messages = []
        async for msg in channel.history(limit=5, around=discord.Object(id=message_id)):
            messages.append(msg)
        
        # Sort by timestamp to get chronological order
        messages.sort(key=lambda x: x.created_at)
        
        # Check for thinkso pairs in the surrounding messages
        thinkso_pairs = []
        orphaned_bot_messages = []
        
        # First pass: find user->bot pairs and orphaned bot messages
        for i, msg in enumerate(messages):
            if msg.author.bot:
                continue
                
            thinkso = find_thinkso(msg.content)
            if thinkso:
                # Look for bot response in nearby messages
                for j in range(max(0, i-2), min(len(messages), i+3)):
                    if i == j:
                        continue
                    bot_msg = messages[j]
                    if bot_msg.author.id == bot.user.id:
                        bot_thinkso = find_thinkso(bot_msg.content)
                        if bot_thinkso:
                            thinkso_pairs.append((i, j, thinkso, bot_thinkso))
        
        # Second pass: find bot->user pairs (reversed order)
        for i, msg in enumerate(messages):
            if not msg.author.bot or msg.author.id != bot.user.id:
                continue
                
            bot_thinkso = find_thinkso(msg.content)
            if bot_thinkso:
                # Look for user response in nearby messages
                found_user_pair = False
                for j in range(max(0, i-2), min(len(messages), i+3)):
                    if i == j:
                        continue
                    user_msg = messages[j]
                    if not user_msg.author.bot:
                        user_thinkso = find_thinkso(user_msg.content)
                        if user_thinkso:
                            # Found a bot->user pair, add it as reversed
                            thinkso_pairs.append((j, i, user_thinkso, bot_thinkso))
                            found_user_pair = True
                            break
                
                # If no user pair found, mark as orphaned
                if not found_user_pair:
                    orphaned_bot_messages.append((i, msg))
        
        # Handle orphaned bot messages (delete them)
        for idx, orphaned_msg in orphaned_bot_messages:
            try:
                await orphaned_msg.delete()
                bot.logger.info(f"Deleted orphaned bot thinkso message in {channel.name}")
            except Exception as e:
                bot.logger.error(f"Failed to delete orphaned bot message: {e}")
        
        # If we have exactly one pair, check if it's suspicious
        if len(thinkso_pairs) == 1:
            user_idx, bot_idx, user_thinkso, bot_thinkso = thinkso_pairs[0]
            user_message = messages[user_idx]
            
            # Determine expected bot response based on user type
            if user_message.author.id in THINKSO_OPPOSITE_USERS:
                # User should get opposite response
                expected_bot_thinkso = get_opposite_thinkso(user_thinkso)
                is_suspicious = (user_thinkso == bot_thinkso)
            elif user_message.author.id in THINKSO_FOLLOW_USERS:
                # User should get same response
                expected_bot_thinkso = user_thinkso
                is_suspicious = (user_thinkso != bot_thinkso)
            else:
                # Default to opposite behavior for unknown users
                expected_bot_thinkso = get_opposite_thinkso(user_thinkso)
                is_suspicious = (user_thinkso == bot_thinkso)
            
            # Check if the response is suspicious
            if is_suspicious:
                
                # Check if this is a reversed order (bot->user instead of user->bot)
                # This would indicate someone deleted the user's original message
                is_reversed_order = (bot_idx < user_idx)
                
                # Find the correct emoji
                emojis = await bot.fetch_application_emojis()
                correct_emoji = discord.utils.get(emojis, name=expected_bot_thinkso)
                
                if correct_emoji:
                    if is_reversed_order:
                        # For reversed order, delete the bot message and post a new one
                        # This simulates the bot responding after the user
                        bot_message = messages[bot_idx]
                        await bot_message.delete()
                        await channel.send(str(correct_emoji))
                        bot.logger.warning(f"Fixed reversed thinkso order in {channel.name} - deleted bot message and reposted")
                    else:
                        # Normal case - edit the bot's message
                        bot_message = messages[bot_idx]
                        await bot_message.edit(content=str(correct_emoji))
                    
                    # Determine target user for notifications
                    target_user = trigger_user if trigger_user else user_message.author
                    
                    # Log the manipulation attempt
                    bot.logger.warning(
                        f"Detected thinkso manipulation in channel {channel.name} (ID: {channel.id}) "
                        f"by user {target_user.name} (ID: {target_user.id}). "
                        f"Fixed bot response from {bot_thinkso} to {expected_bot_thinkso}."
                    )
                    
                    # PM the user with FORSENSMUG emote
                    dm_sent = False
                    try:
                        # Find the FORSENSMUG emoji
                        emojis = await bot.fetch_application_emojis()
                        forsen_smug = discord.utils.get(emojis, name='FORSENSMUG')
                        if forsen_smug:
                            await target_user.send(str(forsen_smug))
                            dm_sent = True
                        else:
                            # Fallback if emoji not found
                            await target_user.send("😏")
                            dm_sent = True
                    except discord.Forbidden:
                        # User has DMs disabled or blocked the bot
                        bot.logger.info(f"Could not send FORSENSMUG DM to {target_user.name} - DMs disabled")
                    except Exception as e:
                        bot.logger.error(f"Failed to send FORSENSMUG DM: {e}")
                    
                    # If DM failed, post FORSENSMUG in the chat
                    if not dm_sent:
                        try:
                            emojis = await bot.fetch_application_emojis()
                            forsen_smug = discord.utils.get(emojis, name='FORSENSMUG')
                            if forsen_smug:
                                await channel.send(f"{target_user.mention} {str(forsen_smug)}")
                            else:
                                await channel.send(f"{target_user.mention} 😏")
                        except Exception as e:
                            bot.logger.error(f"Failed to send FORSENSMUG to channel: {e}")
                    
                    # Send a log message to a designated channel if configured
                    if 'log_channel_id' in config and config['log_channel_id']:
                        try:
                            log_channel = bot.get_channel(config['log_channel_id'])
                            if log_channel:
                                embed = discord.Embed(
                                    title="🚨 Thinkso Manipulation Detected",
                                    description=f"User {target_user.mention} attempted to manipulate thinkso responses in {channel.mention}",
                                    color=0xFF0000,
                                    timestamp=discord.utils.utcnow()
                                )
                                embed.add_field(name="Channel", value=channel.mention, inline=True)
                                embed.add_field(name="User", value=target_user.mention, inline=True)
                                embed.add_field(name="Action", value=f"Fixed bot response from {bot_thinkso} to {expected_bot_thinkso} (user said {user_thinkso})", inline=False)
                                await log_channel.send(embed=embed)
                        except Exception as e:
                            bot.logger.error(f"Failed to send log message: {e}")
    
    except Exception as e:
        bot.logger.error(f"Error checking thinkso pair: {e}")

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    """
    Handle message edits to detect thinkso manipulation.
    """
    # Ignore bot messages
    if before.author.bot:
        return
    
    # Check if the edit involved a thinkso
    before_thinkso = find_thinkso(before.content)
    after_thinkso = find_thinkso(after.content)
    
    if before_thinkso or after_thinkso:
        # Add a small delay to ensure the edit is processed
        await asyncio.sleep(0.5)
        await check_thinkso_pair(after.channel, after.id, before.author)

@bot.event
async def on_message_delete(message: discord.Message) -> None:
    """
    Handle message deletes to detect thinkso manipulation.
    """
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if the deleted message contained a thinkso
    thinkso = find_thinkso(message.content)
    if thinkso:
        # Add a small delay to ensure the delete is processed
        await asyncio.sleep(0.5)
        await check_thinkso_pair(message.channel, message.id, message.author)


asyncio.run(init_db())
asyncio.run(load_cogs())



bot.run(config["token"])



