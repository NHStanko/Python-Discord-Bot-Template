"""Thinkso emoji responses and edit/delete handling."""

import asyncio
import random
import re

import discord
from discord.ext import commands

from helpers.message_handler import is_dollar_amount_message


async def idontthinkso(bot, message: discord.Message) -> None:
    import re

    # [<Emoji id=1399554109014675507 name='NOIDONTTHINKSO' animated=True managed=False>, <Emoji id=1399554124390858852 name='YESIDOTHINKSO' animated=True managed=False>]
    # If the message is only one of the emojis, respond based on the weighted behavior rules
    # Check if the message is only a single emoji (It looks like <a:NOIDONTTHINKSO:803763692210487357>)

    # Regex to match a single emoji in the message (animated or static)
    emoji_pattern = r"^<a?:([^:]+):\d+>$"
    match = re.match(emoji_pattern, message.content.strip())

    if match:
        emoji_name = match.group(1).upper()  # Work with uppercase names

        if emoji_name in ["NOIDONTTHINKSO", "YESIDOTHINKSO"]:
            emojis = await bot.fetch_application_emojis()
            roll = random.random()
            # 50% chance to ignore the message
            if roll < 0.5:
                return

            if roll < 0.875:  # Next 37.5% reverses the emoji
                target_name = (
                    "YESIDOTHINKSO"
                    if emoji_name == "NOIDONTTHINKSO"
                    else "NOIDONTTHINKSO"
                )
            else:  # Remaining 12.5% matches the emoji
                target_name = emoji_name

            target_emoji = discord.utils.get(emojis, name=target_name)
            if target_emoji:
                await message.channel.send(str(target_emoji))


def find_thinkso(content: str):
    """
    Find a thinkso emoji in the message content.
    Returns the emoji name in uppercase if found, False otherwise.
    """
    # Regex to match emoji patterns (both animated and static)
    emoji_pattern = r"<a?:([^:]+):\d+>"
    matches = re.findall(emoji_pattern, content)

    for match in matches:
        emoji_name = match.upper()
        if emoji_name in ["NOIDONTTHINKSO", "YESIDOTHINKSO"]:
            return emoji_name

    return False


def get_opposite_thinkso(thinkso: str):
    """
    Given a thinkso emoji name, return the opposite one.
    """
    if thinkso == "NOIDONTTHINKSO":
        return "YESIDOTHINKSO"
    elif thinkso == "YESIDOTHINKSO":
        return "NOIDONTTHINKSO"
    else:
        raise ValueError(f"Invalid thinkso: {thinkso}")


async def check_thinkso_pair(
    bot,
    channel: discord.TextChannel,
    message_id: int,
    trigger_user: discord.User = None,
) -> None:
    """
    Check for thinkso pairs around a message and fix if manipulation is detected.
    """
    try:
        # Get messages around the target message (4 above, 4 below)
        messages = []
        async for msg in channel.history(limit=9, around=discord.Object(id=message_id)):
            messages.append(msg)

        # Sort by timestamp to get chronological order
        messages.sort(key=lambda x: x.created_at)

        # Check for thinkso pairs in the surrounding messages
        thinkso_pairs = []
        orphaned_bot_messages = []

        # Track which message pairs we've already found to avoid duplicates
        found_pairs = set()

        # First pass: find user->bot pairs and orphaned bot messages
        for i, msg in enumerate(messages):
            if msg.author.bot:
                continue

            thinkso = find_thinkso(msg.content)
            if thinkso:
                # Look for bot response in nearby messages
                for j in range(max(0, i - 4), min(len(messages), i + 5)):
                    if i == j:
                        continue
                    bot_msg = messages[j]
                    if bot_msg.author.id == bot.user.id:
                        bot_thinkso = find_thinkso(bot_msg.content)
                        if bot_thinkso:
                            # Check if we've already found this pair
                            pair_key = (min(i, j), max(i, j))
                            if pair_key not in found_pairs:
                                found_pairs.add(pair_key)
                                thinkso_pairs.append(
                                    (i, j, thinkso, bot_thinkso, False)
                                )  # False = normal order
                            break

        # Second pass: find bot->user pairs (reversed order)
        for i, msg in enumerate(messages):
            if not msg.author.bot or msg.author.id != bot.user.id:
                continue

            bot_thinkso = find_thinkso(msg.content)
            if bot_thinkso:
                # Look for user response in nearby messages
                found_user_pair = False
                for j in range(max(0, i - 4), min(len(messages), i + 5)):
                    if i == j:
                        continue
                    user_msg = messages[j]
                    if not user_msg.author.bot:
                        user_thinkso = find_thinkso(user_msg.content)
                        if user_thinkso:
                            # Check if we've already found this pair
                            pair_key = (min(i, j), max(i, j))
                            if pair_key not in found_pairs:
                                found_pairs.add(pair_key)
                                # Found a bot->user pair, add it as reversed
                                # Store with a flag to indicate reversed order
                                thinkso_pairs.append(
                                    (j, i, user_thinkso, bot_thinkso, True)
                                )  # True = reversed
                                found_user_pair = True
                                break
                            else:
                                # Even though we skipped it, this bot message is part of a valid pair
                                found_user_pair = True
                                break

                # If no user pair found, mark as orphaned
                if not found_user_pair:
                    orphaned_bot_messages.append((i, msg))

        # Handle orphaned bot messages (delete them)
        for idx, orphaned_msg in orphaned_bot_messages:
            try:
                await orphaned_msg.delete()
                bot.logger.info(
                    f"Deleted orphaned bot thinkso message in {channel.name}"
                )
            except Exception as e:
                bot.logger.error(f"Failed to delete orphaned bot message: {e}")

        # Only fix if there's exactly one pair (ignore if there are multiple thinksos)
        if len(thinkso_pairs) == 1:
            user_idx, bot_idx, user_thinkso, bot_thinkso, is_reversed = thinkso_pairs[0]
            user_message = messages[user_idx]
            bot_message = messages[bot_idx]

            # Bot can now either mirror or flip the emoji; treat both as valid responses
            expected_bot_thinkso = get_opposite_thinkso(user_thinkso)
            allowed_bot_thinksos = {user_thinkso, expected_bot_thinkso}
            is_suspicious = bot_thinkso not in allowed_bot_thinksos

            # For reversed order, always check if the bot's response is one of the allowed options
            if is_reversed:
                is_suspicious = bot_thinkso not in allowed_bot_thinksos

            # Check if the response is suspicious
            if is_suspicious:
                # Find the correct emoji
                emojis = await bot.fetch_application_emojis()
                correct_emoji = discord.utils.get(emojis, name=expected_bot_thinkso)

                if correct_emoji:
                    # Always edit the bot's message (never delete/repost)
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
                        forsen_smug = discord.utils.get(emojis, name="FORSENSMUG")
                        if forsen_smug:
                            await target_user.send(str(forsen_smug))
                            dm_sent = True
                        else:
                            # Fallback if emoji not found
                            await target_user.send("😏")
                            dm_sent = True
                    except discord.Forbidden:
                        # User has DMs disabled or blocked the bot
                        bot.logger.info(
                            f"Could not send FORSENSMUG DM to {target_user.name} - DMs disabled"
                        )
                    except Exception as e:
                        bot.logger.error(f"Failed to send FORSENSMUG DM: {e}")

                    # If DM failed, post FORSENSMUG in the chat
                    if not dm_sent:
                        try:
                            emojis = await bot.fetch_application_emojis()
                            forsen_smug = discord.utils.get(emojis, name="FORSENSMUG")
                            if forsen_smug:
                                await channel.send(
                                    f"{target_user.mention} {str(forsen_smug)}"
                                )
                            else:
                                await channel.send(f"{target_user.mention} 😏")
                        except Exception as e:
                            bot.logger.error(
                                f"Failed to send FORSENSMUG to channel: {e}"
                            )

                    # Send a log message to a designated channel if configured
                    if "log_channel_id" in bot.config and bot.config["log_channel_id"]:
                        try:
                            log_channel = bot.get_channel(bot.config["log_channel_id"])
                            if log_channel:
                                embed = discord.Embed(
                                    title="🚨 Thinkso Manipulation Detected",
                                    description=f"User {target_user.mention} attempted to manipulate thinkso responses in {channel.mention}",
                                    color=0xFF0000,
                                    timestamp=discord.utils.utcnow(),
                                )
                                embed.add_field(
                                    name="Channel", value=channel.mention, inline=True
                                )
                                embed.add_field(
                                    name="User", value=target_user.mention, inline=True
                                )
                                embed.add_field(
                                    name="Action",
                                    value=f"Fixed bot response from {bot_thinkso} to {expected_bot_thinkso} (user said {user_thinkso})",
                                    inline=False,
                                )
                                await log_channel.send(embed=embed)
                        except Exception as e:
                            bot.logger.error(f"Failed to send log message: {e}")

    except Exception as e:
        bot.logger.error(f"Error checking thinkso pair: {e}")


async def handle_message_edit(
    bot, before: discord.Message, after: discord.Message
) -> None:
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
        await check_thinkso_pair(bot, after.channel, after.id, before.author)


async def handle_message_delete(bot, message: discord.Message) -> None:
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
        await check_thinkso_pair(bot, message.channel, message.id, message.author)


class Thinkso(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or is_dollar_amount_message(message.content):
            return
        await idontthinkso(self.bot, message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await handle_message_edit(self.bot, before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        await handle_message_delete(self.bot, message)


async def setup(bot):
    await bot.add_cog(Thinkso(bot))
