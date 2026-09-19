from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from helpers.tts_service import PocketTTSService
from helpers.ai import AIHelper, load_ai_helper_from_config
from helpers.tts_sequence import (
    RandomSpeechSegment,
    SilenceSegment,
    SpeechSegment,
    parse_tts_sequence,
)
from helpers.voice_store import VoiceStore


logger = logging.getLogger("discord_bot")
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".webm"}
BROCK_USER_ID = 157644363227201536
BROCK_TTS_CHANCE = 100
BROCK_TTS_VOICE = "northernlion"
BROCK_TTS_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "brock_game_tts.txt"
EPHEMERAL_LIFETIME = 5


def should_trigger_brock_tts(user_id: int) -> bool:
    return user_id == BROCK_USER_ID and secrets.randbelow(BROCK_TTS_CHANCE) == 0


def game_names(activities: tuple[discord.BaseActivity, ...]) -> tuple[str, ...]:
    names = []
    for activity in activities:
        name = getattr(activity, "name", None)
        if activity.type is discord.ActivityType.playing and isinstance(name, str):
            if cleaned_name := name.strip():
                names.append(cleaned_name)
    return tuple(names)


def newly_started_game(
    before: tuple[discord.BaseActivity, ...], after: tuple[discord.BaseActivity, ...]
) -> str | None:
    previous = set(game_names(before))
    return next((name for name in game_names(after) if name not in previous), None)


def valid_brock_monologue(text: str) -> bool:
    paragraphs = [part.strip() for part in text.strip().split("\n\n") if part.strip()]
    word_count = len(text.split())
    return len(paragraphs) == 2 and 250 <= word_count <= 375


class VoiceVolumeView(discord.ui.View):
    def __init__(
        self, store: VoiceStore, voice: str, volume: float, owner_id: int
    ) -> None:
        super().__init__(timeout=180)
        self.store = store
        self.voice = voice
        self.volume = volume
        self.owner_id = owner_id

    @property
    def content(self) -> str:
        return (
            f"Adjusting `{self.voice}` volume: **{round(self.volume * 100)}%**\n"
            "Changes apply after you press **Confirm**."
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Only the owner who opened this panel can use it.",
            ephemeral=True,
            delete_after=EPHEMERAL_LIFETIME,
        )
        return False

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content=self.content, view=self)

    @discord.ui.button(label="Vol Down", style=discord.ButtonStyle.gray)
    async def volume_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.volume = max(0.0, round(self.volume - 0.2, 2))
        await self.refresh(interaction)

    @discord.ui.button(label="Vol Up", style=discord.ButtonStyle.gray)
    async def volume_up(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.volume = min(4.0, round(self.volume + 0.2, 2))
        await self.refresh(interaction)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.red)
    async def reset(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.volume = 2.0
        await self.refresh(interaction)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        profile = self.store.set_volume(self.voice, self.volume)
        self.stop()
        await interaction.response.edit_message(
            content=(
                f"✅ `{profile.slug}` volume set to "
                f"**{round(profile.volume * 100)}%**."
            ),
            view=None,
        )


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
        self.ai_helper: AIHelper | None = None
        self._brock_locks: dict[int, asyncio.Lock] = {}

    async def delete_original_response_later(
        self, interaction: discord.Interaction
    ) -> None:
        await asyncio.sleep(EPHEMERAL_LIFETIME)
        try:
            await interaction.delete_original_response()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            logger.exception("Could not delete an ephemeral TTS response")

    def schedule_original_response_deletion(
        self, interaction: discord.Interaction
    ) -> None:
        asyncio.create_task(self.delete_original_response_later(interaction))

    def brock_prompt(self, game: str) -> str:
        template = BROCK_TTS_PROMPT.read_text(encoding="utf-8")
        return template.replace("[INSERT GAME HERE]", game).replace(
            "[OPTIONAL]", "Not provided"
        )

    async def generate_brock_monologue(self, game: str) -> str | None:
        if self.ai_helper is None:
            self.ai_helper = load_ai_helper_from_config(self.bot, logger=logger)
        if self.ai_helper is None:
            logger.error("Brock game TTS skipped: Gemini is not configured")
            return None

        response, error = await self.ai_helper.generate_content(
            prompt=self.brock_prompt(game),
            thinking_level="high",
            enable_web_search=True,
        )
        if error or not response:
            logger.error("Brock game TTS generation failed: %s", error or "empty response")
            return None
        response = response.strip()
        if not valid_brock_monologue(response):
            logger.error(
                "Brock game TTS generation had invalid format (%s words)",
                len(response.split()),
            )
            return None
        return response

    async def maybe_play_brock_game_tts(
        self, member: discord.Member, channel: discord.abc.Connectable, game: str
    ) -> None:
        if not should_trigger_brock_tts(member.id):
            return

        lock = self._brock_locks.setdefault(member.guild.id, asyncio.Lock())
        if lock.locked():
            logger.info("Brock game TTS skipped: another greeting is being prepared")
            return

        async with lock:
            output: Path | None = None
            try:
                client = member.guild.voice_client
                if client is not None and client.is_playing():
                    logger.info("Brock game TTS skipped: the bot is already speaking")
                    return

                try:
                    profile = self.store.get_voice(BROCK_TTS_VOICE)
                    self.store.state_path(profile.slug)
                except (KeyError, FileNotFoundError, ValueError) as exc:
                    logger.error("Brock game TTS voice is unavailable: %s", exc)
                    return

                monologue = await self.generate_brock_monologue(game)
                if monologue is None:
                    return

                current_channel = getattr(member.voice, "channel", None)
                if current_channel != channel:
                    logger.info("Brock game TTS skipped: Brock left the voice channel")
                    return

                client = member.guild.voice_client
                if client is None:
                    client = await channel.connect()
                elif client.channel != channel:
                    await client.move_to(channel)
                if client.is_playing():
                    logger.info("Brock game TTS skipped: the bot is already speaking")
                    return

                output = await self.tts.synthesize(profile.slug, monologue)
                client = member.guild.voice_client
                current_channel = getattr(member.voice, "channel", None)
                if (
                    client is None
                    or client.channel != channel
                    or current_channel != channel
                    or client.is_playing()
                ):
                    return

                loop = asyncio.get_running_loop()
                cleanup_path = output

                def finished(error: Exception | None) -> None:
                    cleanup_path.unlink(missing_ok=True)
                    if error:
                        loop.call_soon_threadsafe(
                            logger.error, "Discord Brock TTS playback failed: %s", error
                        )

                client.play(
                    discord.FFmpegPCMAudio(
                        str(output), options=f"-af volume={profile.volume:.2f}"
                    ),
                    after=finished,
                )
                output = None
                logger.info(
                    "Played Northernlion game monologue for Brock while playing %s", game
                )
            except Exception:
                logger.exception("Brock game TTS generation/playback failed")
            finally:
                if output is not None:
                    output.unlink(missing_ok=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or member.id != BROCK_USER_ID:
            return
        if after.channel is None or before.channel == after.channel:
            return
        games = game_names(member.activities)
        if games:
            await self.maybe_play_brock_game_tts(member, after.channel, games[0])

    @commands.Cog.listener()
    async def on_presence_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if after.bot or after.id != BROCK_USER_ID or after.voice is None:
            return
        game = newly_started_game(before.activities, after.activities)
        if game:
            await self.maybe_play_brock_game_tts(after, after.voice.channel, game)

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
            "Only a bot owner can manage voice profiles.",
            ephemeral=True,
            delete_after=EPHEMERAL_LIFETIME,
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
            await interaction.response.send_message(
                "Join a voice channel first.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return
        if not text.strip() or len(text) > self.max_text_length:
            await interaction.response.send_message(
                f"Text must be 1-{self.max_text_length} characters.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return

        await interaction.response.defer(ephemeral=True)
        output: Path | None = None
        try:
            profile = self.store.get_voice(voice)
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

            client.play(
                discord.FFmpegPCMAudio(
                    str(output), options=f"-af volume={profile.volume:.2f}"
                ),
                after=finished,
            )
            output = None
            await interaction.edit_original_response(
                content=f"Speaking with `{self.store.normalize_name(voice)}`."
            )
        except Exception as exc:
            logger.exception("Speech generation/playback failed")
            await interaction.edit_original_response(content=f"Could not speak: {exc}")
        finally:
            if output is not None:
                output.unlink(missing_ok=True)
            self.schedule_original_response_deletion(interaction)

    @tts_group.command(name="sequence", description="Speak a sequence of voices and pauses")
    @app_commands.describe(
        script="Example: (forsen) Hello (pause) 2 (random) Hi there"
    )
    async def sequence(self, interaction: discord.Interaction, script: str) -> None:
        member = interaction.user
        if not interaction.guild or not isinstance(member, discord.Member) or not member.voice:
            await interaction.response.send_message(
                "Join a voice channel first.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            await interaction.response.send_message(
                "The bot is already speaking; try again in a moment.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return

        try:
            segments = parse_tts_sequence(
                script, max_segments=20, max_text_length=self.max_text_length
            )
            random_voices = [
                profile for profile in self.store.list_voices() if profile.trained
            ]
            resolved_segments = []
            for segment in segments:
                if isinstance(segment, RandomSpeechSegment):
                    if not random_voices:
                        raise ValueError("No trained voices are available for `(random)`")
                    selected = secrets.choice(random_voices)
                    resolved_segments.append(SpeechSegment(selected.slug, segment.text))
                else:
                    resolved_segments.append(segment)
            segments = resolved_segments
            profiles = {
                segment.voice: self.store.get_voice(segment.voice)
                for segment in segments
                if isinstance(segment, SpeechSegment)
            }
        except Exception as exc:
            await interaction.response.send_message(
                f"Invalid sequence: {exc}",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return

        await interaction.response.defer(ephemeral=True)
        generated: list[Path] = []
        output: Path | None = None
        try:
            parts: list[tuple[Path | None, float]] = []
            for index, segment in enumerate(segments, start=1):
                if isinstance(segment, SilenceSegment):
                    await interaction.edit_original_response(
                        content=(
                            f"⏸️ Adding a {segment.duration:g}-second pause "
                            f"({index}/{len(segments)})..."
                        )
                    )
                    parts.append((None, segment.duration))
                    continue

                profile = profiles[segment.voice]
                await interaction.edit_original_response(
                    content=(
                        f"🗣️ Generating `{profile.slug}` "
                        f"({index}/{len(segments)})..."
                    )
                )
                audio = await self.tts.synthesize(profile.slug, segment.text)
                generated.append(audio)
                parts.append((audio, profile.volume))

            await interaction.edit_original_response(
                content="🎛️ Combining the voices and pauses..."
            )
            output = await self.tts.combine_sequence(parts)

            channel = member.voice.channel
            client = interaction.guild.voice_client
            if client is None:
                client = await channel.connect()
            elif client.channel != channel:
                await client.move_to(channel)
            if client.is_playing():
                raise RuntimeError("The bot started playing something else; try again")

            loop = asyncio.get_running_loop()
            cleanup_path = output

            def finished(error: Exception | None) -> None:
                cleanup_path.unlink(missing_ok=True)
                if error:
                    loop.call_soon_threadsafe(
                        logger.error, "Discord TTS sequence playback failed: %s", error
                    )

            client.play(discord.FFmpegPCMAudio(str(output)), after=finished)
            output = None
            await interaction.edit_original_response(
                content=f"✅ Playing a {len(segments)}-part TTS sequence."
            )
        except Exception as exc:
            logger.exception("TTS sequence generation/playback failed")
            await interaction.edit_original_response(
                content=f"❌ Could not play sequence: {exc}"
            )
        finally:
            for path in generated:
                path.unlink(missing_ok=True)
            if output is not None:
                output.unlink(missing_ok=True)
            self.schedule_original_response_deletion(interaction)

    @tts_group.command(name="list", description="List globally available voices")
    async def voices(self, interaction: discord.Interaction) -> None:
        voices = self.store.list_voices()
        if not voices:
            await interaction.response.send_message(
                "No voices have been trained yet.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return
        lines = []
        for voice in voices:
            status = " · staged changes" if voice.needs_retrain else ""
            if not voice.trained:
                status = " · needs training"
            lines.append(
                f"`{voice.slug}` · {voice.sample_count} sample(s) · "
                f"{round(voice.volume * 100)}% volume{status}"
            )
        await interaction.response.send_message(
            "**Global voices**\n" + "\n".join(lines),
            ephemeral=True,
            delete_after=EPHEMERAL_LIFETIME,
        )

    @tts_group.command(name="volume", description="Adjust a voice's playback volume")
    @app_commands.describe(voice="Voice")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def volume(self, interaction: discord.Interaction, voice: str) -> None:
        if not await self.require_owner(interaction):
            return
        try:
            profile = self.store.get_voice(voice)
            view = VoiceVolumeView(
                self.store, profile.slug, profile.volume, interaction.user.id
            )
            await interaction.response.send_message(
                view.content,
                view=view,
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not adjust voice volume: {exc}",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
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
            if youtube_url is not None:
                await interaction.edit_original_response(
                    content=(
                        f"⏬ Downloading a {duration}-second YouTube clip "
                        f"starting at {start} seconds..."
                    )
                )
            else:
                await interaction.edit_original_response(
                    content="📎 Reading and validating the attached recording..."
                )
            filename, content = await self.read_sample_source(
                sample, youtube_url, start, duration
            )
            await interaction.edit_original_response(
                content="💾 Saving the reference recording..."
            )
            self.store.create_voice(name, interaction.user.id)
            created = True
            self.store.add_sample(name, filename, content)
            await interaction.edit_original_response(
                content=(
                    "🧠 Building the voice profile... The first run may take longer "
                    "while Pocket TTS downloads and loads its model."
                )
            )
            await self.tts.train(name)
            await interaction.edit_original_response(
                content=(
                    f"✅ Voice `{self.store.normalize_name(name)}` is trained and "
                    "globally available."
                )
            )
        except Exception as exc:
            if created:
                try:
                    await self.tts.delete(name)
                except Exception:
                    logger.exception("Could not roll back failed voice creation")
            logger.exception("Voice training failed")
            await interaction.edit_original_response(content=f"❌ Training failed: {exc}")
        finally:
            self.schedule_original_response_deletion(interaction)

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
            await interaction.edit_original_response(
                content=(
                    f"Sample added to `{profile.slug}`. Run `/tts retrain` when ready."
                )
            )
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"Could not add sample: {exc}"
            )
        finally:
            self.schedule_original_response_deletion(interaction)

    @tts_group.command(name="retrain", description="Rebuild a voice from its samples")
    @app_commands.describe(voice="Voice")
    @app_commands.autocomplete(voice=voice_autocomplete)
    async def retrain(self, interaction: discord.Interaction, voice: str) -> None:
        if not await self.require_owner(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.tts.train(voice)
            await interaction.edit_original_response(
                content=f"Voice `{self.store.normalize_name(voice)}` was rebuilt."
            )
        except Exception as exc:
            logger.exception("Voice retraining failed")
            await interaction.edit_original_response(
                content=f"Retraining failed: {exc}"
            )
        finally:
            self.schedule_original_response_deletion(interaction)

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
                "**Retained samples**\n" + "\n".join(lines),
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not list samples: {exc}",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
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
                delete_after=EPHEMERAL_LIFETIME,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not remove sample: {exc}",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
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
                "Nothing deleted. Set `confirm` to true.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
            return
        try:
            slug = self.store.normalize_name(voice)
            await self.tts.delete(slug)
            await interaction.response.send_message(
                f"Permanently deleted `{slug}` and all of its files.",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Could not delete voice: {exc}",
                ephemeral=True,
                delete_after=EPHEMERAL_LIFETIME,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TTS(bot))
