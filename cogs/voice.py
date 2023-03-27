from discord.ext import commands
from discord.ext.commands import Context
# Import ffmpeg
from discord import FFmpegPCMAudio
import os
from pathlib import Path
from helpers import checks, db_manager
import discord
import random
from yt_dlp import YoutubeDL
from discord import app_commands
# Import List
from typing import List
import subprocess


async def play_sound(guild: discord.Guild, sound: str):
    if not guild.voice_client:
        await guild.author.voice.channel.connect()
    if guild.voice_client.is_playing():
        guild.voice_client.stop()
    guild.voice_client.play(FFmpegPCMAudio(executable="ffmpeg", source=f"sounds/{sound}"))

def get_sound():
    sounds = [Path(sound).stem for sound in os.listdir("sounds")]
    return sounds

def get_sound_with_extension() -> dict:
    # Filename : basename
    sounds = {Path(sound).stem : sound for sound in os.listdir("sounds")}
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
        sounds = get_sound()
        return [
            app_commands.Choice(name=sound, value=sound)
            for sound in sounds if current.lower() in sound.lower()
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

        # Don't forget to remove "pass", I added this just because there's no content in the method.
        
        # is the user in a voice channel?
        if not context.author.voice:
            await context.send("You are not connected to a voice channel.", ephemeral=True)
            return
        # is the bot already in a voice channel?
        if context.voice_client:
            # is the user in a different channel?
            if context.author.voice.channel != context.voice_client.channel:
                # is the bot playing?
                if context.guild.voice_client.is_playing():
                    await context.send("I am already playing music in another channel.", ephemeral=True)
                    return
                else:
                    await context.voice_client.move_to(context.author.voice.channel)
                
        else:
            await context.author.voice.channel.connect()
        
        # search the sounds folder for the query and remove the extension
        # get base file name withot extension
        
        sounds = get_sound_with_extension()
        
        if sound not in sounds.keys():
            await context.send("This sound does not exist.", ephemeral=True, delete_after=10)
            return
        
        await play_sound(context, sounds[sound])
        # Close the context
        await context.send(f"Playing {sound}.", ephemeral=True, delete_after=1)
        #async def add_play(user_id: int, server_id: int, song: str) -> int:
        await db_manager.add_play(context.author.id, context.guild.id, sound)
        # If it was not a slash command, delete the message
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

        # Don't forget to remove "pass", I added this just because there's no content in the method.
        
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
            await context.send("I have sent you a DM with all the sounds.", ephemeral=True, delete_after=5)
            
    @commands.hybrid_command(
        name="stop",
        description="This command stops the bot from playing music.",
    )
    async def stop(self, context: Context):
        await stop_playing(context.guild)
        await context.send("Stopped playing.", ephemeral=True, delete_after=5)
        if not context.interaction:
            await context.message.delete()
            
    @commands.hybrid_command(
        name="random",
        description="This command plays a random sound.",
    )
    async def random(self, context: Context):
        sounds = get_sound_with_extension()
        sound = random.choice(list(sounds.keys()))
        await play_sound(context, sounds[sound])
        await context.send(f"Playing {sound}.", ephemeral=True, delete_after=3)

    # Commands that are associated with adding sounds
    
    @commands.hybrid_group(
        name="add",
        description="This command adds a sound.",
    )
    async def add(self, context: Context, *, sound: str):
        pass
    
    @add.command(
        base="add",
        name="youtube",
        description="This command adds a sound from youtube.",
    )
    async def add_youtube(self, context: Context, link: str, name: str,*,  start: int = 1, end: int = -1):
        
        # Download the video
        
        # Get the video
        configs = {
            'format': 'bestaudio/best',
            
        }
        
        
        with YoutubeDL(configs) as ydl:
            # Download the video as an mp3 file
            
            ydl.download([link])


        
    
    
    





# And then we finally add the cog to the bot so that it can load, unload, reload and use it's content.
async def setup(bot):
    await bot.add_cog(Voice(bot))
