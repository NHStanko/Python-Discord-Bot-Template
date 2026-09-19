import asyncio
import logging
import os
import random
import re
import shutil
import tempfile
from pathlib import Path
from time import perf_counter
from typing import List
from urllib.parse import urlparse

import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from yt_dlp import YoutubeDL

from helpers import checks, db_manager

logger = logging.getLogger("discord_bot")

SOUNDS_DIR = Path("./sounds")
SOUNDS_TEMP_DIR = SOUNDS_DIR / "temp"
SOUNDS_ORIGINAL_DIR = SOUNDS_DIR / "original"
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
SOUND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


def validate_sound_name(name: str) -> str:
    """Validate a user-provided sound name before using it as a filename."""
    if not isinstance(name, str):
        raise ValueError("Sound names must be text")
    name = name.strip()
    if not SOUND_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Sound names must start with a letter or number and contain only "
            "letters, numbers, spaces, underscores, hyphens, or periods"
        )
    return name


def validate_youtube_url(link: str) -> str:
    """Accept only HTTPS URLs hosted by YouTube."""
    parsed = urlparse(link.strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or hostname not in YOUTUBE_HOSTS:
        raise ValueError("Use a valid YouTube or youtu.be URL")
    return parsed.geturl()


def validate_time_range(start: int, duration: int) -> None:
    """Bound conversion times to avoid unbounded legacy downloads."""
    if not isinstance(start, int) or start < 0 or start > 86_400:
        raise ValueError("Start time must be between 0 and 86400 seconds")
    if not isinstance(duration, int) or not 1 <= duration <= 30:
        raise ValueError("Duration must be between 1 and 30 seconds")


def conversion_ffmpeg_args(
    source: Path, destination: Path, start: int, duration: int
) -> list[str]:
    """Build an argument-vector FFmpeg conversion command."""
    validate_time_range(start, duration)
    arguments = ["-y", "-ss", str(start), "-i", str(source)]
    arguments.extend(["-t", str(duration)])
    arguments.extend(["-vn", str(destination)])
    return arguments


async def run_ffmpeg(arguments: list[str], timeout: float = 120) -> None:
    """Run FFmpeg without blocking the event loop or invoking a shell."""
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("FFmpeg timed out") from exc
    if process.returncode:
        detail = stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError(
            f"FFmpeg failed: {detail[-1] if detail else 'unknown error'}"
        )

async def play_sound(context: Context, sound: str):
    if not context.voice_client:
        await context.author.voice.channel.connect()
    if context.voice_client.is_playing():
        context.voice_client.stop()
    start = perf_counter()
    logger.info(f"Playing {sound}")
    
    context.voice_client.play(
        FFmpegPCMAudio(executable="ffmpeg", source=f"sounds/{sound}", options="-af volume=0.75")
    )
    
    logger.info(f"Started playing {sound} after {perf_counter()-start} seconds")


def get_sound(dir="./sounds"):
    return [path.stem for path in Path(dir).iterdir() if path.is_file()]


def get_sound_with_extension(dir: str = "./sounds") -> dict:
    # Filename : basename
    return {path.stem: path.name for path in Path(dir).iterdir() if path.is_file()}


async def stop_playing(guild: discord.Guild):
    if guild.voice_client:
        if guild.voice_client.is_playing():
            guild.voice_client.stop()


# Here we name the cog and create a new class for the cog.
class Voice(commands.Cog, name="voice"):
    def __init__(self, bot):
        self.bot = bot

    async def require_sound_manager(self, context: Context) -> bool:
        """Allow bot owners or moderators to mutate the sound library."""
        permissions = getattr(context.author, "guild_permissions", None)
        can_manage = bool(getattr(permissions, "manage_messages", False))
        configured_owners = self.bot.config.get("owners", [])
        is_owner = context.author.id in configured_owners or await self.bot.is_owner(
            context.author
        )
        if can_manage or is_owner:
            return True
        await context.send(
            "You do not have permission to manage sounds.",
            ephemeral=True,
            delete_after=5,
        )
        return False

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
        sounds = sorted(get_sound())
        current = current.strip().lower()
        matching_sounds = [
            sound for sound in sounds if not current or current in sound.lower()
        ]

        return [
            app_commands.Choice(name=sound, value=sound)
            for sound in matching_sounds[:25]
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
        try:
            sound = validate_sound_name(sound)
        except ValueError:
            await context.send("That sound name is invalid.", ephemeral=True)
            return

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
            subject = f"User {user.display_name}" if user else "Nobody"
            await context.send(f"{subject} has not played any sounds yet.")
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
        if not context.author.voice:
            await context.send(
                "You are not connected to a voice channel.", ephemeral=True
            )
            return
        if context.voice_client and context.author.voice.channel != context.voice_client.channel:
            await context.send(
                "You are not connected to my voice channel.", ephemeral=True
            )
            return

        sounds = get_sound_with_extension()
        if not sounds:
            await context.send("No sounds are available.", ephemeral=True)
            return
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

        if not await self.require_sound_manager(context):
            return

        try:
            sound = validate_sound_name(sound)
        except ValueError:
            await context.send("That sound name is invalid.", ephemeral=True)
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

        if not await self.require_sound_manager(context):
            return

        try:
            sound = validate_sound_name(sound)
        except ValueError:
            await context.send("That sound name is invalid.", ephemeral=True)
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
        duration: int = 30,
    ):
        """Adds a sound from youtube.

        Args:
            context (Context): discord context
            link (str): link to the youtube video
            name (str): name that the sound will have
            start (int, optional): start time for the video. Defaults to 0.
            duration (int, optional): duration of the sound. Defaults to 30.
        """

        if not await self.require_sound_manager(context):
            return
        try:
            name = validate_sound_name(name)
            link = validate_youtube_url(link)
            validate_time_range(start, duration)
        except ValueError as exc:
            await context.send(str(exc), ephemeral=True, delete_after=5)
            return

        # Check if the sound already exists
        if name in get_sound():
            await context.send(
                "This sound already exists.", ephemeral=True, delete_after=5
            )
            return

        try:
            SOUNDS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            SOUNDS_ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                dir=SOUNDS_TEMP_DIR, prefix="youtube-"
            ) as temp_dir:
                temp_path = Path(temp_dir)
                configs = {
                    "format": "bestaudio/best",
                    "outtmpl": str(temp_path / "source.%(ext)s"),
                    "noplaylist": True,
                    "max_downloads": 1,
                    "max_filesize": 50 * 1024 * 1024,
                    "playlistend": 1,
                    "retries": 2,
                    "socket_timeout": 30,
                }

                await context.send(
                    "Downloading the video", ephemeral=True, delete_after=3
                )

                def download() -> None:
                    with YoutubeDL(configs) as ydl:
                        ydl.download([link])

                await asyncio.to_thread(download)
                candidates = [
                    path
                    for path in temp_path.iterdir()
                    if path.is_file() and path.name.startswith("source.")
                ]
                if len(candidates) != 1:
                    raise ValueError("The download did not produce one audio file")
                source = candidates[0]
                destination = temp_path / "converted.mp3"

                await context.send(
                    "Converting the video", ephemeral=True, delete_after=3
                )
                await run_ffmpeg(
                    conversion_ffmpeg_args(source, destination, start, duration)
                )
                if not destination.is_file():
                    raise RuntimeError("FFmpeg did not produce an output file")
                await asyncio.gather(
                    asyncio.to_thread(
                        shutil.copyfile, destination, SOUNDS_DIR / f"{name}.mp3"
                    ),
                    asyncio.to_thread(
                        shutil.copyfile,
                        destination,
                        SOUNDS_ORIGINAL_DIR / f"{name}.mp3",
                    ),
                )
        except Exception as e:
            await context.send(
                f"Something went wrong while downloading the video: {e}",
                ephemeral=True,
                delete_after=5,
            )
            return

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
        if not await self.require_sound_manager(context):
            return
        try:
            sound = validate_sound_name(sound)
        except ValueError:
            await context.send("That sound name is invalid.", ephemeral=True)
            return

        # Create the view

        # Send the message
        # Check if the sound exists
        if sound not in get_sound():
            await context.send(
                "This sound does not exist.", ephemeral=True, delete_after=10
            )
            return
        view = SoundModifyView(sound, context.author.id)
        await context.send(f"Modifying `{sound}`", view=view)
        
    
        
class SoundModifyView(discord.ui.View):
    def __init__(self, sound: str, authorized_user_id: int):
        super().__init__()
        self.sound = validate_sound_name(sound)
        self.authorized_user_id = authorized_user_id
        self.sound_ext = get_sound_with_extension()[self.sound]
        # Set the title of the view
        self.title = f"Modifying {self.sound}"
        
        # Check if the sound exists in the original folder
        originals = get_sound(dir="./sounds/original")
        if self.sound not in originals:
            # Copy from sounds to sounds/original
            # Find the full name of the sound with the extension
            sounds = get_sound_with_extension(dir="./sounds")
            shutil.copy(f"./sounds/{sounds[self.sound]}", f"./sounds/original/{sounds[self.sound]}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.authorized_user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this sound editor can use it.",
            ephemeral=True,
        )
        return False

    async def _apply_volume(self, factor: float) -> None:
        source = SOUNDS_DIR / self.sound_ext
        SOUNDS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            suffix=source.suffix, dir=SOUNDS_TEMP_DIR, delete=False
        )
        destination = Path(handle.name)
        handle.close()
        try:
            await run_ffmpeg(
                [
                    "-y",
                    "-i",
                    str(source),
                    "-af",
                    f"volume={factor}",
                    str(destination),
                ]
            )
            await asyncio.to_thread(shutil.copyfile, destination, source)
        finally:
            destination.unlink(missing_ok=True)
        
    

    # Callback for the "Vol Down" button
    @discord.ui.button(label="Vol Down", style=discord.ButtonStyle.gray)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Modify and save to a temp file
        await self._apply_volume(0.8)
        await interaction.response.send_message(f"`{self.sound}` decreased 20%", ephemeral=True, delete_after=5)

    @discord.ui.button(label="Vol Up", style=discord.ButtonStyle.gray)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Send a response with the button label
        # Modify and save to a temp file
        await self._apply_volume(1.2)
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
        await asyncio.to_thread(
            shutil.copyfile,
            SOUNDS_ORIGINAL_DIR / sounds[self.sound],
            SOUNDS_DIR / sounds[self.sound],
        )
        await interaction.message.edit(view=None, content=f'`{self.sound}` has been reset.')
        
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None, content=f'`{self.sound}` has been modified.')

# And then we finally add the cog to the bot so that it can load, unload,
# reload and use it's content.
async def setup(bot):
    await bot.add_cog(Voice(bot))
