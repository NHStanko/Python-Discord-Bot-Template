from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from helpers.tts_service import PocketTTSService
from helpers.voice_store import VoiceStore


logger = logging.getLogger("discord_bot")
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".webm"}


class TTS(commands.Cog, name="tts"):
    tts_group = app_commands.Group(name="tts", description="Generate and manage speech")
    samples_group = app_commands.Group(
        name="samples",
        description="Manage retained voice samples",
        parent=tts_group,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        tts_config = bot.config.get("tts", {})
        data_dir = Path(os.getenv("TTS_DATA_DIR", tts_config.get("data_dir", "data/tts")))
        self.max_attachment_bytes = int(
            os.getenv(
                "MAX_VOICE_ATTACHMENT_BYTES",
                tts_config.get("max_attachment_bytes", 20 * 1024 * 1024),
            )
        )
        self.max_samples_per_voice = int(
            os.getenv(
                "MAX_SAMPLES_PER_VOICE", tts_config.get("max_samples_per_voice", 10)
            )
        )
        self.max_text_length = int(
            os.getenv("MAX_TTS_TEXT_LENGTH", tts_config.get("max_text_length", 1500))
        )
        language = os.getenv("POCKET_TTS_LANGUAGE", tts_config.get("language", "english"))
        self.store = VoiceStore(data_dir)
        self.tts = PocketTTSService(self.store, language)

    async def voice_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        typed = current.casefold()
        return [
            app_commands.Choice(name=voice.display_name, value=voice.slug)
            for voice in self.store.list_voices()
            if typed in voice.slug.casefold() or typed in voice.display_name.casefold()
        ][:25]

    async def sample_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        voice_name = getattr(interaction.namespace, "voice", None)
        if not voice_name:
            return []
        try:
            samples = self.store.list_samples(voice_name)
        except (KeyError, ValueError):
            return []
        typed = current.casefold()
        return [
            app_commands.Choice(
                name=f"{sample.original_filename} · {sample.id[:8]}", value=sample.id
            )
            for sample in samples
            if typed in sample.original_filename.casefold() or typed in sample.id
        ][:25]

    async def require_owner(self, interaction: discord.Interaction) -> bool:
        owner_ids = {int(owner) for owner in self.bot.config.get("owners", [])}
        if interaction.user.id in owner_ids or await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message(
            "Only a bot owner can manage voice profiles.", ephemeral=True
        )
        return False

    async def read_attachment(self, attachment: discord.Attachment) -> bytes:
        if attachment.size > self.max_attachment_bytes:
            limit = self.max_attachment_bytes // 1024 // 1024
            raise ValueError(f"Attachment is larger than {limit} MB")
        if Path(attachment.filename).suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            raise ValueError("Use a WAV, MP3, FLAC, M4A, OGG, OPUS, or WEBM attachment")
        content = await attachment.read()
        if len(content) > self.max_attachment_bytes:
            raise ValueError("Attachment exceeds the configured size limit")
        return content

    async def read_sample_source(
        self,
        sample: discord.Attachment | None,
        youtube_url: str | None,
        start: int,
        duration: int,
    ) -> tuple[str, bytes]:
        if (sample is None) == (youtube_url is None):
            raise ValueError("Provide either one audio attachment or one YouTube URL")
        if sample is not None:
            return sample.filename, await self.read_attachment(sample)
        return await self.tts.download_youtube_sample(
            youtube_url or "", start, duration, self.max_attachment_bytes
        )

    @tts_group.command(name="speak", description="Speak with a trained global voice")
    @app_commands.describe(voice="Voice", text="Text to speak")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def speak(self, interaction: discord.Interaction, voice: str, text: str) -> None:
        member = interaction.user
        if not interaction.guild or not isinstance(member, discord.Member) or not member.voice:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        if not text.strip() or len(text) > self.max_text_length:
            await interaction.response.send_message(
                f"Text must be 1-{self.max_text_length} characters.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        output: Path | None = None
        try:
            output = await self.tts.synthesize(voice, text.strip())
            channel = member.voice.channel
            client = interaction.guild.voice_client
            if client is None:
                client = await channel.connect()
            elif client.channel != channel:
                await client.move_to(channel)
            if client.is_playing():
                raise RuntimeError("The bot is already speaking; try again in a moment")

            loop = asyncio.get_running_loop()
            cleanup_path = output

            def finished(error: Exception | None) -> None:
                cleanup_path.unlink(missing_ok=True)
                if error:
                    loop.call_soon_threadsafe(
                        logger.error, "Discord TTS playback failed: %s", error
                    )

            client.play(discord.FFmpegPCMAudio(str(output)), after=finished)
            output = None
            await interaction.followup.send(
                f"Speaking with `{self.store.normalize_name(voice)}`.", ephemeral=True
            )
        except Exception as exc:
            logger.exception("Speech generation/playback failed")
            await interaction.followup.send(f"Could not speak: {exc}", ephemeral=True)
        finally:
            if output is not None:
                output.unlink(missing_ok=True)

    @tts_group.command(name="list", description="List globally available voices")
    async def voices(self, interaction: discord.Interaction) -> None:
        voices = self.store.list_voices()
        if not voices:
            await interaction.response.send_message(
                "No voices have been trained yet.", ephemeral=True
            )
            return
        lines = []
        for voice in voices:
            status = " · staged changes" if voice.needs_retrain else ""
            if not voice.trained:
                status = " · needs training"
            lines.append(f"`{voice.slug}` · {voice.sample_count} sample(s){status}")
        await interaction.response.send_message(
            "**Global voices**\n" + "\n".join(lines), ephemeral=True
        )

    @tts_group.command(name="train", description="Train a new global voice")
    @app_commands.describe(
        name="Unique voice name",
        sample="Voice recording (use this or youtube_url)",
        youtube_url="YouTube video (use this or sample)",
        start="Clip start time in seconds",
        duration="Clip length in seconds (maximum 30)",
    )
    async def train(
        self,
        interaction: discord.Interaction,
        name: str,
        sample: discord.Attachment | None = None,
        youtube_url: str | None = None,
        start: app_commands.Range[int, 0, 86400] = 0,
        duration: app_commands.Range[int, 1, 30] = 30,
    ) -> None:
        if not await self.require_owner(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        created = False
        try:
            filename, content = await self.read_sample_source(
                sample, youtube_url, start, duration
            )
            self.store.create_voice(name, interaction.user.id)
            created = True
            self.store.add_sample(name, filename, content)
            await self.tts.train(name)
            await interaction.followup.send(
                f"Voice `{self.store.normalize_name(name)}` is trained and globally available.",
                ephemeral=True,
            )
        except Exception as exc:
            if created:
                try:
                    await self.tts.delete(name)
                except Exception:
                    logger.exception("Could not roll back failed voice creation")
            logger.exception("Voice training failed")
            await interaction.followup.send(f"Training failed: {exc}", ephemeral=True)

    @samples_group.command(name="add", description="Stage another voice sample")
    @app_commands.describe(
        voice="Voice",
        sample="Voice recording (use this or youtube_url)",
        youtube_url="YouTube video (use this or sample)",
        start="Clip start time in seconds",
        duration="Clip length in seconds (maximum 30)",
    )
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def add_sample(
        self,
        interaction: discord.Interaction,
        voice: str,
        sample: discord.Attachment | None = None,
        youtube_url: str | None = None,
        start: app_commands.Range[int, 0, 86400] = 0,
        duration: app_commands.Range[int, 1, 30] = 30,
    ) -> None:
        if not await self.require_owner(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            profile = self.store.get_voice(voice)
            if profile.sample_count >= self.max_samples_per_voice:
                raise ValueError(
                    f"A voice may have at most {self.max_samples_per_voice} samples"
                )
            filename, content = await self.read_sample_source(
                sample, youtube_url, start, duration
            )
            self.store.add_sample(voice, filename, content)
            await interaction.followup.send(
                f"Sample added to `{profile.slug}`. Run `/tts retrain` when ready.",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(f"Could not add sample: {exc}", ephemeral=True)

    @tts_group.command(name="retrain", description="Rebuild a voice from its samples")
    @app_commands.describe(voice="Voice")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def retrain(self, interaction: discord.Interaction, voice: str) -> None:
        if not await self.require_owner(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.tts.train(voice)
            await interaction.followup.send(
                f"Voice `{self.store.normalize_name(voice)}` was rebuilt.", ephemeral=True
            )
        except Exception as exc:
            logger.exception("Voice retraining failed")
            await interaction.followup.send(f"Retraining failed: {exc}", ephemeral=True)

    @samples_group.command(name="list", description="List retained samples for a voice")
    @app_commands.describe(voice="Voice")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def samples(self, interaction: discord.Interaction, voice: str) -> None:
        if not await self.require_owner(interaction):
            return
        try:
            samples = self.store.list_samples(voice)
            lines = [f"`{sample.id[:8]}` · {sample.original_filename}" for sample in samples]
            await interaction.response.send_message(
                "**Retained samples**\n" + "\n".join(lines), ephemeral=True
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not list samples: {exc}", ephemeral=True
            )

    @samples_group.command(name="remove", description="Remove one retained sample")
    @app_commands.describe(voice="Voice", sample="Retained sample")
    @app_commands.autocomplete(voice=voice_autocomplete, sample=sample_autocomplete)
    async def remove_sample(
        self, interaction: discord.Interaction, voice: str, sample: str
    ) -> None:
        if not await self.require_owner(interaction):
            return
        try:
            removed = self.store.remove_sample(voice, sample)
            await interaction.response.send_message(
                f"Removed `{removed.original_filename}`. Run `/tts retrain` to apply it.",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not remove sample: {exc}", ephemeral=True
            )

    @tts_group.command(name="delete", description="Permanently erase a voice")
    @app_commands.describe(voice="Voice", confirm="Confirm permanent deletion")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def delete(
        self, interaction: discord.Interaction, voice: str, confirm: bool
    ) -> None:
        if not await self.require_owner(interaction):
            return
        if not confirm:
            await interaction.response.send_message(
                "Nothing deleted. Set `confirm` to true.", ephemeral=True
            )
            return
        try:
            slug = self.store.normalize_name(voice)
            await self.tts.delete(slug)
            await interaction.response.send_message(
                f"Permanently deleted `{slug}` and all of its files.", ephemeral=True
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not delete voice: {exc}", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TTS(bot))
