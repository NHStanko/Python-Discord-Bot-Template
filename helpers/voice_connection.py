import asyncio
import logging
import time
from collections import defaultdict

import discord


def human_member_count(channel: discord.VoiceChannel) -> int:
    """Return the number of non-bot members currently in a voice channel."""
    return sum(not member.bot for member in channel.members)


class VoiceConnectionManager:
    """Serialize automatic voice connection changes within each guild."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._retry_after: dict[int, float] = {}
        self._retry_delay: dict[int, float] = {}
        self._guild_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle_voice_state_update(self, member, after) -> None:
        if member.bot:
            return

        async with self._guild_locks[member.guild.id]:
            target = after.channel
            member_channel = getattr(getattr(member, "voice", None), "channel", None)
            if member_channel != target:
                target = None
            await self._reconcile(member.guild, target)

    async def reconcile_guild(self, guild) -> None:
        """Recover missed events and dropped connections from current cached state."""
        if guild.unavailable:
            return
        async with self._guild_locks[guild.id]:
            client = guild.voice_client
            current = getattr(client, "channel", None)
            candidates = ([current] if current is not None else []) + list(
                guild.voice_channels
            )
            target = next(
                (channel for channel in candidates if human_member_count(channel)), None
            )
            if target is None:
                self._reset_retry(guild)
            await self._reconcile(guild, target)

    def _reset_retry(self, guild) -> None:
        self._retry_after.pop(guild.id, None)
        self._retry_delay.pop(guild.id, None)

    def _defer_retry(self, guild) -> None:
        delay = min(self._retry_delay.get(guild.id, 15.0) * 2, 300.0)
        self._retry_delay[guild.id] = delay
        self._retry_after[guild.id] = time.monotonic() + delay
        self.logger.warning(
            "Voice recovery for guild %s will retry in %.0fs", guild.id, delay
        )

    async def connect(self, channel):
        """Connect or move to ``channel`` without racing automatic joins."""
        guild = channel.guild
        async with self._guild_locks[guild.id]:
            client = guild.voice_client
            if client is not None and not client.is_connected():
                await client.disconnect(force=True)
                client = None
            if client is not None:
                if getattr(client, "channel", None) != channel:
                    await client.move_to(channel)
                return client

            try:
                # This manager owns retries. Library-level reconnects can survive
                # a timed-out call and collide with later voice-state events.
                client = await channel.connect(reconnect=False)
                self._reset_retry(guild)
                return client
            except BaseException:
                await self._clean_up_failed_connection(guild, channel)
                raise

    async def _reconcile(self, guild, target) -> None:
        voice_client = guild.voice_client

        if voice_client is not None:
            current_channel = getattr(voice_client, "channel", None)
            if (
                voice_client.is_connected()
                and current_channel is not None
                and human_member_count(current_channel) > 0
            ):
                self._reset_retry(guild)
                return

            channel_name = str(current_channel) if current_channel is not None else "voice"
            reason = (
                "channel is empty"
                if current_channel is not None and not human_member_count(current_channel)
                else "voice connection is unhealthy"
            )
            try:
                # force=True also removes a half-open client left by a failed handshake.
                await voice_client.disconnect(force=True)
                self.logger.info(
                    "Disconnected from %s: %s.", channel_name, reason,
                )
            except Exception:
                self.logger.exception("Failed to disconnect from %s", channel_name)
                return

        if target is None or human_member_count(target) == 0:
            return
        if time.monotonic() < self._retry_after.get(guild.id, 0):
            return

        # A manual command or another listener may have connected while the stale
        # client above was being cleaned up.
        if guild.voice_client is not None:
            return

        try:
            client = await target.connect(reconnect=False)
        except (TimeoutError, discord.ClientException, discord.ConnectionClosed) as exc:
            self.logger.warning(
                "Could not connect to %s: %s: %s",
                target,
                type(exc).__name__,
                exc,
            )
            await self._clean_up_failed_connection(guild, target)
            self._defer_retry(guild)
            return
        except asyncio.CancelledError:
            await self._clean_up_failed_connection(guild, target)
            raise
        except Exception:
            self.logger.exception("Could not connect to %s", target)
            await self._clean_up_failed_connection(guild, target)
            self._defer_retry(guild)
            return

        self._reset_retry(guild)
        # A leave event can arrive while connect() is awaiting Discord. Do not
        # leave the bot parked alone until another event happens to clean it up.
        if human_member_count(target) == 0:
            await client.disconnect(force=True)
            self.logger.info(
                "Disconnected from %s because I was alone in it.", target
            )
            return

        self.logger.info("Connected to %s because humans are present.", target)

    async def _clean_up_failed_connection(self, guild, target) -> None:
        client = guild.voice_client
        if client is None or getattr(client, "channel", None) != target:
            return
        try:
            await client.disconnect(force=True)
        except Exception:
            self.logger.debug(
                "Failed to clean up the voice client for %s", target, exc_info=True
            )
