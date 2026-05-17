""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
import time
import os
import subprocess
import logging
from pathlib import Path

from helpers import checks, db_manager


class Owner(commands.Cog, name="owner"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="sync",
        description="Synchonizes the slash commands.",
    )
    @app_commands.describe(scope="The scope of the sync. Can be `global` or `guild`")
    @checks.is_owner()
    async def sync(self, context: Context, scope: str) -> None:
        """
        Synchonizes the slash commands.

        :param context: The command context.
        :param scope: The scope of the sync. Can be `global` or `guild`.
        """

        if scope == "global":
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="Slash commands have been globally synchronized.",
                color=0x9C84EF,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.copy_global_to(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="Slash commands have been synchronized in this guild.",
                color=0x9C84EF,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
        )
        await context.send(embed=embed)

    @commands.command(
        name="unsync",
        description="Unsynchonizes the slash commands.",
    )
    @app_commands.describe(
        scope="The scope of the sync. Can be `global`, `current_guild` or `guild`"
    )
    @checks.is_owner()
    async def unsync(self, context: Context, scope: str) -> None:
        """
        Unsynchonizes the slash commands.

        :param context: The command context.
        :param scope: The scope of the sync. Can be `global`, `current_guild` or `guild`.
        """

        if scope == "global":
            context.bot.tree.clear_commands(guild=None)
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="Slash commands have been globally unsynchronized.",
                color=0x9C84EF,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.clear_commands(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="Slash commands have been unsynchronized in this guild.",
                color=0x9C84EF,
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description="The scope must be `global` or `guild`.", color=0xE02B2B
        )
        await context.send(embed=embed)

    @commands.command(
        name="load",
        description="Load a cog",
    )
    @app_commands.describe(cog="The name of the cog to load")
    @checks.is_owner()
    async def load(self, context: Context, cog: str) -> None:
        """
        The bot will load the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to load.
        """
        try:
            await self.bot.load_extension(f"cogs.{cog}")
        except Exception as e:
            embed = discord.Embed(
                description=f"Could not load the `{cog}` cog. Error {e}", color=0xE02B2B
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully loaded the `{cog}` cog.", color=0x9C84EF
        )
        await context.send(embed=embed)

    @commands.command(
        name="unload",
        description="Unloads a cog.",
    )
    @app_commands.describe(cog="The name of the cog to unload")
    @checks.is_owner()
    async def unload(self, context: Context, cog: str) -> None:
        """
        The bot will unload the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to unload.
        """
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
        except Exception:
            embed = discord.Embed(
                description=f"Could not unload the `{cog}` cog.", color=0xE02B2B
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully unloaded the `{cog}` cog.", color=0x9C84EF
        )
        await context.send(embed=embed)

    @commands.command(
        name="reload",
        description="Reloads a cog.",
    )
    @app_commands.describe(cog="The name of the cog to reload")
    @checks.is_owner()
    async def reload(self, context: Context, cog: str) -> None:
        """
        The bot will reload the given cog.

        :param context: The hybrid command context.
        :param cog: The name of the cog to reload.
        """
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
        except Exception:
            embed = discord.Embed(
                description=f"Could not reload the `{cog}` cog.", color=0xE02B2B
            )
            await context.send(embed=embed)
            return
        embed = discord.Embed(
            description=f"Successfully reloaded the `{cog}` cog.", color=0x9C84EF
        )
        await context.send(embed=embed)

    @commands.command(
        name="shutdown",
        description="Make the bot shutdown.",
    )
    @checks.is_owner()
    async def shutdown(self, context: Context) -> None:
        """
        Shuts down the bot.

        :param context: The hybrid command context.
        """
        embed = discord.Embed(description="Shutting down. Bye! :wave:", color=0x9C84EF)
        await context.send(embed=embed)
        await self.bot.close()
        await time.sleep(1)
        await self.bot.login(self.bot.config["token"])
        

    @commands.hybrid_command(
        name="say",
        description="The bot will say anything you want.",
    )
    @checks.is_owner()
    async def say(self, context: Context, *, message: str) -> None:
        """
        The bot will say anything you want.

        :param context: The hybrid command context.
        :param message: The message that should be repeated by the bot.
        """
        await context.channel.send(message)
        await context.reply("Message sent!", ephemeral=True, delete_after=5)

    @commands.command(
        name="embed",
        description="The bot will say anything you want, but within embeds.",
    )
    @app_commands.describe(message="The message that should be repeated by the bot")
    @checks.is_owner()
    async def embed(self, context: Context, *, message: str) -> None:
        """
        The bot will say anything you want, but using embeds.

        :param context: The hybrid command context.
        :param message: The message that should be repeated by the bot.
        """
        embed = discord.Embed(description=message, color=0x9C84EF)
        await context.message.delete()
        await context.send(embed=embed)

    @commands.command(
        name="sync_emotes",
        description="Syncs emotes by running the emote scraper script.",
    )
    @checks.is_owner()
    async def sync_emotes(self, context: Context) -> None:
        """
        Synchronizes emotes by running the emote scraper script.

        :param context: The command context.
        """
        embed = discord.Embed(
            description="Starting emote synchronization. This may take a few minutes...",
            color=0x9C84EF,
        )
        await context.send(embed=embed)
        
        try:
            # Navigate to the emotes directory
            current_dir = os.getcwd()
            emotes_dir = os.path.join(current_dir, "emotes")
            
            # Run the emote scraper script and capture output
            process = subprocess.Popen(
                ["python", "emote_scraper.py"], 
                cwd=emotes_dir,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            # Log the output instead of sending it
            logger = logging.getLogger('discord')
            logger.info("Emote sync stdout: %s", stdout)
            if stderr:
                logger.error("Emote sync stderr: %s", stderr)
            
            if process.returncode == 0:
                embed = discord.Embed(
                    description="Emote synchronization completed successfully!",
                    color=0x9C84EF,
                )
            else:
                embed = discord.Embed(
                    description=f"Emote synchronization failed with return code {process.returncode}",
                    color=0xE02B2B,
                )
            
            await context.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                description=f"An error occurred during emote synchronization: {e}",
                color=0xE02B2B,
            )
            await context.send(embed=embed)

    @commands.hybrid_command(
        name="patchnotes",
        description="Shows the latest patchnotes of the bot.",
    )
    @checks.is_owner()
    async def patchnotes(self, context: Context) -> None:
        """
        Shows the latest patchnotes of the bot.

        :param context: The command context.
        """
        updates_path = Path(__file__).resolve().parents[1] / "UPDATES.md"
        updates = updates_path.read_text(encoding="utf-8")
        lines = [
            line.removeprefix("* ")
            for line in updates.splitlines()
            if line.startswith("* ")
        ]

        embed = discord.Embed(title="Latest Update", color=0x9C84EF)
        embed.description = "\n".join(f"• {line}" for line in lines)
        await context.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Owner(bot))
