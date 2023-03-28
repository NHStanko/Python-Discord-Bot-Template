import os
import random
import subprocess
from pathlib import Path

# Import List
from typing import List

import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from yt_dlp import YoutubeDL

from helpers import checks, db_manager
import re
import shutil


async def play_sound(guild: discord.Guild, sound: str):
    if not guild.voice_client:
        await guild.author.voice.channel.connect()
    if guild.voice_client.is_playing():
        guild.voice_client.stop()
    guild.voice_client.play(
        FFmpegPCMAudio(executable="ffmpeg", source=f"sounds/{sound}")
    )


def get_sound():
    sounds = [Path(sound).stem for sound in os.listdir("sounds")]
    return sounds


def get_sound_with_extension(dir: str = './sounds') -> dict:
    # Filename : basename
    sounds = {Path(sound).stem: sound for sound in os.listdir(dir)}
    return sounds


async def stop_playing(guild: discord.Guild):
    if guild.voice_client:
        if guild.voice_client.is_playing():
            guild.voice_client.stop()


# Here we name the cog and create a new class for the cog.
class Voice(commands.Cog, name="voice"):
    def __init__(self, bot):
        self.bot = bot

    async def play_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """autocomplete for play command, returns a list of choices that have the current input in them

        Args:
            interaction (discord.Interaction): discord interaction
            current (str): current input

        Returns:
            List[app_commands.Choice[str]]: list of choices that have the current input in them
        """        
        sounds = get_sound()
        return [
            app_commands.Choice(name=sound, value=sound)
            for sound in sounds
            if current.lower() in sound.lower()
        ]

    @commands.hybrid_command(
        name="play",
        description="This command plays a song.",
        aliases=["p", "s"],
        with_application_command=True,
    )
    @checks.not_blacklisted()
    @app_commands.autocomplete(sound=play_autocomplete)
    async def play(self, context: Context, *, sound: str):
        """
        This command plays a song.

        :param context: The application command context.
        :param query: The query to search for.
        """
        # Do your stuff here

        # Don't forget to remove "pass", I added this just because there's no
        # content in the method.

        # is the user in a voice channel?
        if not context.author.voice:
            await context.send(
                "You are not connected to a voice channel.", ephemeral=True
            )
            return
        # is the bot already in a voice channel?
        if context.voice_client:
            # is the user in a different channel?
            if context.author.voice.channel != context.voice_client.channel:
                # is the bot playing?
                if context.guild.voice_client.is_playing():
                    await context.send(
                        "I am already playing music in another channel.", ephemeral=True
                    )
                    return
                else:
                    await context.voice_client.move_to(context.author.voice.channel)

        else:
            await context.author.voice.channel.connect()

        sounds = get_sound_with_extension()

        if sound not in sounds.keys():
            await context.send(
                "This sound does not exist.", ephemeral=True, delete_after=10
            )
            return

        await play_sound(context, sounds[sound])
        await context.send(f"Playing {sound}.", ephemeral=True, delete_after=10)
        await db_manager.add_play(context.author.id, context.guild.id, sound)
        if not context.interaction:
            await context.message.delete()

    @commands.hybrid_command(
        name="sounds",
        description="This command lists all the sounds.",
    )
    async def sounds(self, context: Context):
        """
        This command lists all the sounds.

        :param context: The application command context.
        """
        # Do your stuff here

        # Don't forget to remove "pass", I added this just because there's no
        # content in the method.

        sounds = sorted(get_sound())

        max_length = 2000

        # Send a message before the max length is reached
        buffer_message = "Available sounds:\n"
        for sound in sounds:
            if len(buffer_message) + len(sound) + 2 > max_length:
                embed = discord.Embed(
                    description=buffer_message,
                    color=0xE02B2B,
                )
                await context.author.send(embed=embed)
                buffer_message = ""
            buffer_message += f"{sound}, "

        # Send the rest of the message
        embed = discord.Embed(
            description=buffer_message,
            color=0xE02B2B,
        )
        # Send it in a DM
        await context.author.send(embed=embed)

        # If it was not a slash command, delete the message
        if not context.interaction:
            await context.message.delete()
        else:
            await context.send(
                "I have sent you a DM with all the sounds.",
                ephemeral=True,
                delete_after=5,
            )

    @commands.hybrid_command(
        name="stop",
        description="This command stops the bot from playing music.",
    )
    async def stop(self, context: Context):
        """stops the bot from playing music in the current server.

        Args:
            context (Context): discord.py context object
        """
        # Check if the user is in a voice channel with the bot
        if not context.author.voice:
            await context.send(
                "You are not connected to a voice channel.", ephemeral=True
            )
            return
        if not context.voice_client:
            await context.send(
                "I am not connected to a voice channel.", ephemeral=True
            )
            return
        if context.author.voice.channel != context.voice_client.channel:
            await context.send(
                "You are not connected to my voice channel.", ephemeral=True
            )
            return
        await stop_playing(context.guild)
        await context.send("Stopped playing.", ephemeral=True, delete_after=5)
        if not context.interaction:
            await context.message.delete()

    @commands.hybrid_command(
        name="random",
        description="This command plays a random sound.",
    )
    async def random(self, context: Context):
        """Plays a random sound.

        Args:
            context (Context): discord.py context object
        """
        sounds = get_sound_with_extension()
        sound = random.choice(list(sounds.keys()))
        await play_sound(context, sounds[sound])
        await context.send(f"Playing {sound}.", ephemeral=True, delete_after=3)

    @commands.hybrid_command(
        name="delete",
        description="This command deletes a sound.",
    )
    async def delete(self, context: Context, *, sound: str):
        """This command deletes files from the sounds folder.

        Args:
            context (Context): discord.py context object
            sound (str): sound to delete
        """        
        
        # Check if the user has the permissions to delete messages
        if not context.author.guild_permissions.manage_messages:
            await context.send(
                "You do not have the permissions to delete sounds.",
                ephemeral=True,
                delete_after=5,
            )
            return

        sounds = get_sound_with_extension()

        if sound not in sounds.keys():
            await context.send(
                "This sound does not exist.", ephemeral=True, delete_after=10
            )
            return

        os.remove(f"./sounds/{sounds[sound]}")
        await context.send(f"Deleted {sound}.", ephemeral=True, delete_after=3)
        
    @commands.hybrid_command(
        name="restore",
        description="This command restores a sound.",
    )
    async def restore(self, context: Context, *, sound: str):
        """This command restores a deleted or modified sound.

        Args:
            context (Context): discord.py context object
            sound (str): sound to restore
        """        
        
        # Check if the user has the permissions to delete messages
        if not context.author.guild_permissions.manage_messages:
            await context.send(
                "You do not have the permissions to restore sounds.",
                ephemeral=True,
                delete_after=5,
            )
            return

        sounds = get_sound_with_extension("./sounds/original/")

        if sound not in sounds.keys():
            await context.send(
                "This sound does not exist.", ephemeral=True, delete_after=10
            )
            return

        # Copy from sounds/original to sounds
        shutil.copyfile(f"./sounds/original/{sounds[sound]}", f"./sounds/{sounds[sound]}")
        await context.send(f"Restored {sound}.", ephemeral=True, delete_after=3)

    # Commands that are associated with adding sounds
    @commands.hybrid_group(
        name="add",
        description="This command adds a sound.",
    )
    async def add(self, context: Context, *, sound: str):
        """TBD"""
        await context.send(
            "This command is not implemented yet.", ephemeral=True, delete_after=5
        )
        pass

    @add.command(
        base="add",
        name="youtube",
        description="This command adds a sound from youtube.",
    )
    async def add_youtube(
        self,
        context: Context,
        link: str,
        name: str,
        *,
        start: int = 0,
        duration: int = -1,
    ):
        """Adds a sound from youtube.

        Args:
            context (Context): discord context
            link (str): link to the youtube video
            name (str): name that the sound will have
            start (int, optional): start time for the video. Defaults to 0.
            duration (int, optional): duration of the sound. Defaults to -1.
        """

        # Check if the sound already exists
        if name in get_sound():
            await context.send(
                "This sound already exists.", ephemeral=True, delete_after=5
            )
            return

        # Clear the temp folder
        for file in os.listdir("./sounds/temp"):
            os.remove(f"./sounds/temp/{file}")

        configs = {
            "format": "bestaudio/best",
            "outtmpl": f"./sounds/temp/temp.%(ext)s",
        }

        await context.send(f"Downloading the video", ephemeral=True, delete_after=3)
        # Download the video
        try:
            with YoutubeDL(configs) as ydl:
                ydl.download([link])
        except Exception as e:
            await context.send(
                f"Something went wrong while downloading the video: {e}",
                ephemeral=True,
                delete_after=5,
            )
            return

        await context.send(f"Converting the video", ephemeral=True, delete_after=3)

        extension = re.search(
            r"\.(\w+)$", os.listdir("./sounds/temp")[0]).group(1)

        output = os.system(
            f"ffmpeg -ss {start} -i ./sounds/temp/temp.{extension} {f'-t {duration}' if duration!=-1 else ''} -vn ./sounds/temp/{name}.mp3"
        )

        # Copy to original and sounds
        shutil.copy(f"./sounds/temp/{name}.mp3", f"./sounds/{name}.mp3")
        shutil.copy(f"./sounds/temp/{name}.mp3",
                    f"./sounds/original/{name}.mp3")

        await context.send(f"Added {name}, use /play {name}", ephemeral=True, delete_after=30)
        
        
    


# And then we finally add the cog to the bot so that it can load, unload,
# reload and use it's content.
async def setup(bot):
    await bot.add_cog(Voice(bot))
