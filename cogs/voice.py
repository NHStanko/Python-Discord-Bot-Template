import os
import random
import re
import shutil
from pathlib import Path
from typing import List
import logging

import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from yt_dlp import YoutubeDL

from helpers import checks, db_manager


async def play_sound(guild: discord.Guild, sound: str):
    if not guild.voice_client:
        await guild.author.voice.channel.connect()
    if guild.voice_client.is_playing():
        guild.voice_client.stop()
    guild.voice_client.play(
        FFmpegPCMAudio(executable="ffmpeg", source=f"sounds/{sound}", options="-af volume=0.75")
    )


def get_sound(dir="./sounds"):
    sounds = [Path(sound).stem for sound in os.listdir(dir)]
    return sounds


def get_sound_with_extension(dir: str = "./sounds") -> dict:
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
        # async def add_play(user_id: int, song: str) -> int:
        await db_manager.add_play(context.author.id, sound)
        if not context.interaction:
            await context.message.delete()

    @commands.hybrid_group(
        name="sounds",
        description="This command lists sounds.",
    )
    async def sounds(self, context: Context, *, sound: str):
        """TBD"""
        await context.send(
            "This command is not implemented yet.", ephemeral=True, delete_after=5
        )
        pass
    @sounds.command(
        base="sounds",
        name="list",
        description="This command lists all the sounds.",
    )   
    async def sounds_list(self, context: Context):
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
                # Send it as an emphemeral message
                await context.send(embed=embed, ephemeral=True)
                buffer_message = ""
            buffer_message += f"{sound}, "

        # Send the rest of the message
        embed = discord.Embed(
            description=buffer_message,
            color=0xE02B2B,
        )
        # Send it in a DM
        await context.send(embed=embed, ephemeral=True)

        # If it was not a slash command, delete the message
        if not context.interaction:
            await context.message.delete()
        else:
            await context.send(
                "I have sent you a DM with all the sounds.",
                ephemeral=True,
                delete_after=5,
            )
            
    @sounds.command(
        base="sounds",
        name="count",
        description="This command counts the number of times a sound has been played by a user.",
    )
    @app_commands.autocomplete(sound=play_autocomplete)
    async def count(self, context: Context, *, sound: str, user: discord.User = None):
        """This command counts the number of times a sound has been played.

        Args:
            context (Context): discord.py context object
            sound (str): sound to count
            user (discord.User, optional): user to count. Defaults to None.
        """
        # dbmanager.get_plays(sound, user.id)
        if user is None:
            plays = await db_manager.get_plays(0,sound)
            await context.send(
                f"`{sound}` has been played {plays} times.",
            )
        else:
            plays = await db_manager.get_plays(user.id,sound)
            await context.send(
                f"`{sound}` has been played {plays} times by {user.display_name}.",

            )
            
    @sounds.command(
        base="sounds",
        name="leaderboard",
        description="This command counts the number of times a sound has been played by a user.",
    )
    async def sounds_leaderboard(self, context: Context, *, user: discord.User = None):
        if user is None:
            top_plays = await db_manager.get_leaderboard(0)
        else:
            top_plays = await db_manager.get_leaderboard(user.id)

        if len(top_plays) == 0:
            await context.send(
                f"User {user.display_name} has not played any sounds yet.",
            )
            return

        embed = discord.Embed(
            title=f"Sound leaderboard{f' for {user.display_name}' if user else ''}",
            color=0xE02B2B,
        )
        # enumerate
        for i, (sound,play) in enumerate(top_plays):
            embed.add_field(
                name=f"{i+1}. {sound}",
                value=f"{play} plays",
                inline=True,
            )
        await context.send(embed=embed)
        
        

            
            

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
            await context.send("I am not connected to a voice channel.", ephemeral=True)
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
        shutil.copyfile(
            f"./sounds/original/{sounds[sound]}", f"./sounds/{sounds[sound]}"
        )
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

        extension = re.search(r"\.(\w+)$", os.listdir("./sounds/temp")[0]).group(1)

        output = os.system(
            f"ffmpeg -ss {start} -i ./sounds/temp/temp.{extension} {f'-t {duration}' if duration!=-1 else ''} -vn ./sounds/temp/{name}.mp3"
        )

        # Copy to original and sounds
        shutil.copy(f"./sounds/temp/{name}.mp3", f"./sounds/{name}.mp3")
        shutil.copy(f"./sounds/temp/{name}.mp3", f"./sounds/original/{name}.mp3")

        await context.send(
            f"Added {name}, use /play {name}", ephemeral=True, delete_after=30
        )



    @commands.hybrid_group(
        name="modify",
        description="This command modifies a sound.",
    )
    async def modify(self, context: Context, *, sound: str):
        """TBD"""
        await context.send(
            "This command is not implemented yet.", ephemeral=True, delete_after=5
        )
        pass
    
    @modify.command(
        base="modify",
        name="volume",
        description="This command modifies the volume of a sound.",
    )
    @app_commands.autocomplete(sound=play_autocomplete)
    async def modify_volume(self, context: Context, *, sound: str):
        """TBD"""
        
        # Create the view

        # Send the message
        # Check if the sound exists
        if sound not in get_sound():
            await context.send(
                "This sound does not exist.", ephemeral=True, delete_after=10
            )
            return
        view = SoundModifyView(sound)
        await context.send(f"Modifying `{sound}`", view=view)
        
    
        
class SoundModifyView(discord.ui.View):
    def __init__(self, sound: str):
        super().__init__()
        self.sound = sound
        self.sound_ext = get_sound_with_extension()[sound]
        # Set the title of the view
        self.title = f"Modifying {self.sound}"
        
        # Check if the sound exists in the original folder
        originals = get_sound(dir="./sounds/original")
        if not self.sound in originals:
            # Copy from sounds to sounds/original
            # Find the full name of the sound with the extension
            sounds = get_sound_with_extension(dir="./sounds")
            shutil.copy(f"./sounds/{sounds[self.sound]}", f"./sounds/original/{sounds[self.sound]}")
        
    

    # Callback for the "Vol Down" button
    @discord.ui.button(label="Vol Down", style=discord.ButtonStyle.gray)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Modify and save to a temp file
        output = os.system(f"ffmpeg -i ./sounds/{self.sound_ext} -af volume=0.8 ./sounds/temp/{self.sound_ext} -y")
        # Copy from temp to sounds
        shutil.copy(f"./sounds/temp/{self.sound_ext}", f"./sounds/{self.sound_ext}")
        await interaction.response.send_message(f"`{self.sound}` decreased 20%", ephemeral=True, delete_after=5)

    @discord.ui.button(label="Vol Up", style=discord.ButtonStyle.gray)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Send a response with the button label
        # Modify and save to a temp file
        output = os.system(f"ffmpeg -i ./sounds/{self.sound_ext} -af volume=1.2 ./sounds/temp/{self.sound_ext} -y")
        # Copy from temp to sounds
        shutil.copy(f"./sounds/temp/{self.sound_ext}", f"./sounds/{self.sound_ext}")
        await interaction.response.send_message(f"`{self.sound}` increased 20%", ephemeral=True, delete_after=5)
        
    # @discord.ui.button(label="Play", style=discord.ButtonStyle.blurple)
    # async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     # Send a response with the button label
    #     # Check if the user is in a voice channel with the bot
    #     if not interaction.user.voice:
    #         await interaction.response.send_message(
    #             "You are not connected to a voice channel.", ephemeral=True
    #         )
    #         return
    #     # Is the bot in a voice channel?
    #     if interaction.guild.voice_client:
    #         # Is the user in a different channel?
    #         if interaction.user.voice.channel != interaction.guild.voice_client.channel:
    #             # Is the bot playing?
    #             if interaction.guild.voice_client.is_playing():
    #                 await interaction.response.send_message(
    #                     "I am already playing music in another channel.", ephemeral=True
    #                 )
    #                 return
    #             else:
    #                 await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
    #     else:
    #         await interaction.user.voice.channel.connect()
            
    #     sounds = get_sound_with_extension()
    #     # Start the play in the background so that the bot can respond

        
    @discord.ui.button(label="Reset", style=discord.ButtonStyle.red)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Send a response with the button label
        # copy from sounds/original to sounds
        sounds = get_sound_with_extension(dir="./sounds")
        shutil.copy(f"./sounds/original/{sounds[self.sound]}", f"./sounds/{sounds[self.sound]}")
        await interaction.message.edit(view=None, content=f'`{self.sound}` has been reset.')
        
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None, content=f'`{self.sound}` has been modified.')

# And then we finally add the cog to the bot so that it can load, unload,
# reload and use it's content.
async def setup(bot):
    await bot.add_cog(Voice(bot))
