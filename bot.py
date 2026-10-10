"""Discord bot entrypoint; importing this module performs no startup I/O.

Based on the Python Discord Bot Template, Copyright © Krypton 2019-2023.
"""

import argparse
import logging
import os
import platform
import random
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Bot, Context

import exceptions
from helpers.ai import close_ai_helpers
from helpers.config import load_config, validate_config
from helpers.db_manager import init_db
from helpers.http_client import close_http_session
from helpers.message_handler import is_dollar_amount_message, process_message
from helpers.reddit import close_reddit_client
from helpers.voice_connection import VoiceConnectionManager


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


def configure_logging():
    logger = logging.getLogger("discord_bot")
    if logger.handlers:
        return logger
    # Create a formatter for file handlers.
    file_handler_formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
    )

    # Create the main logger and set its level to DEBUG so all messages are processed.
    logger.setLevel(logging.DEBUG)
    # Some audio/ML dependencies configure the root logger lazily. Keep records from
    # being printed a second time by those late root handlers.
    logger.propagate = False
    logging.getLogger("discord").propagate = False

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

    return logger


class ManagedBot(Bot):
    def __init__(self, config, *, voice_enabled=False, logger=None):
        intents = discord.Intents.default()
        intents.presences = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )
        self.config = config
        self.voice_enabled = voice_enabled
        self.logger = logger or logging.getLogger("discord_bot")
        self.voice_connection_manager = VoiceConnectionManager(self.logger)

    async def setup_hook(self):
        await init_db()
        await self.load_cogs()
        if self.config["sync_commands_globally"]:
            self.logger.info("Syncing commands globally...")
            await self.tree.sync()

    async def close(self):
        self.status_task.cancel()
        try:
            # Unload workers before closing the clients they may still use.
            for extension in list(self.extensions):
                try:
                    await self.unload_extension(extension)
                except Exception:
                    self.logger.exception("Could not unload extension %s", extension)
            await close_ai_helpers(self)
        finally:
            try:
                await close_reddit_client(self)
            finally:
                try:
                    await close_http_session(self)
                finally:
                    await super().close()

    async def on_ready(self) -> None:
        """
        The code in this event is executed when the bot is ready.
        """
        self.logger.info(f"Logged in as {self.user.name}")
        self.logger.info(f"discord.py API version: {discord.__version__}")
        self.logger.info(f"Python version: {platform.python_version()}")
        self.logger.info(
            f"Running on: {platform.system()} {platform.release()} ({os.name})"
        )
        self.logger.info("-------------------")
        if not self.status_task.is_running():
            self.status_task.start()

    async def on_voice_state_update(self, member, before, after) -> None:
        # Abort immediately if voice functionality is disabled.
        if not self.voice_enabled:
            return
        await self.voice_connection_manager.handle_voice_state_update(member, after)

    @tasks.loop(minutes=1.0)
    async def status_task(self) -> None:
        """
        Update the bot's game status.
        """
        statuses = ["gex update"]
        await self.change_presence(activity=discord.Game(random.choice(statuses)))

    async def on_message(self, message: discord.Message) -> None:
        # Ignore bots (including self)
        if message.author == self.user or message.author.bot:
            return

        # Dollar amounts such as "$5" are conversation, not prefix commands.
        if is_dollar_amount_message(message.content):
            return

        # Dispatch to registered handlers
        try:
            await process_message(message)
        finally:
            await self.process_commands(message)

    async def on_command_completion(self, context: Context) -> None:
        """
        The code in this event is executed every time a normal command has been *successfully* executed.

        :param context: The context of the command that has been executed.
        """
        full_command_name = context.command.qualified_name
        split = full_command_name.split(" ")
        executed_command = str(split[0])
        if context.guild is not None:
            self.logger.info(
                f"Executed {executed_command} command in {context.guild.name} (ID: {context.guild.id}) by {context.author} (ID: {context.author.id})"
            )
        else:
            self.logger.info(
                f"Executed {executed_command} command by {context.author} (ID: {context.author.id}) in DMs"
            )

    async def on_command_error(self, context: Context, error) -> None:
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
                self.logger.warning(
                    f"{context.author} (ID: {context.author.id}) tried to execute a command in the guild {context.guild.name} (ID: {context.guild.id}), but the user is blacklisted from using the self."
                )
            else:
                self.logger.warning(
                    f"{context.author} (ID: {context.author.id}) tried to execute a command in the bot's DMs, but the user is blacklisted from using the self."
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
                self.logger.warning(
                    f"{context.author} (ID: {context.author.id}) tried to execute an owner only command in the guild {context.guild.name} (ID: {context.guild.id}), but the user is not an owner of the self."
                )
            else:
                self.logger.warning(
                    f"{context.author} (ID: {context.author.id}) tried to execute an owner only command in the bot's DMs, but the user is not an owner of the self."
                )
        elif isinstance(error, exceptions.GamblingDisabled):
            await context.send("Gambling is disabled on this bot.")
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

    async def load_cogs(self) -> None:
        """
        The code in this function is executed whenever the bot will start.
        """
        voice_enabled = self.voice_enabled
        for file in sorted(os.listdir(Path(__file__).resolve().parent / "cogs")):
            if file.endswith(".py"):
                extension = file[:-3]
                if extension == "voice" and not voice_enabled:
                    self.logger.info(
                        "Skipping voice extension (run with --voice to enable)"
                    )
                    continue
                try:
                    await self.load_extension(f"cogs.{extension}")
                    self.logger.info(f"Loaded extension '{extension}'")
                except Exception as e:
                    exception = f"{type(e).__name__}: {e}"
                    self.logger.error(
                        f"Failed to load extension {extension}\n{exception}"
                    )


def create_bot(config=None, *, config_path=None, voice_enabled=False, logger=None):
    validated = load_config(config_path) if config is None else validate_config(config)
    return ManagedBot(validated, voice_enabled=voice_enabled, logger=logger)


def parse_cli_args(argv=None):
    parser = argparse.ArgumentParser(description="Discord bot controller")
    parser.add_argument("--voice", action="store_true", help="Enable voice playback")
    return parser.parse_args(argv)


def main():
    args = parse_cli_args()
    bot = create_bot(voice_enabled=args.voice)
    bot.logger = configure_logging()
    bot.voice_connection_manager = VoiceConnectionManager(bot.logger)
    bot.run(bot.config["token"])


if __name__ == "__main__":
    main()
