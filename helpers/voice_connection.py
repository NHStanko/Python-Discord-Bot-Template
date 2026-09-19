import asyncio
import logging
from collections import defaultdict

import discord


def human_member_count(channel: discord.VoiceChannel) -> int:
    """Return the number of non-bot members currently in a voice channel."""
    return sum(not member.bot for member in channel.members)


class VoiceConnectionManager:
    """Serialize automatic voice connection changes within each guild."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._guild_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle_voice_state_update(self, member, after) -> None:
        if member.bot:
            return

        async with self._guild_locks[member.guild.id]:
            await self._reconcile(member, after)

    async def connect(self, channel):
        """Connect or move to ``channel`` without racing automatic joins."""
        guild = channel.guild
        async with self._guild_locks[guild.id]:
            client = guild.voice_client
            if client is not None:
                if getattr(client, "channel", None) != channel:
                    await client.move_to(channel)
                return client

            try:
                # This manager owns retries. Library-level reconnects can survive
                # a timed-out call and collide with later voice-state events.
                return await channel.connect(reconnect=False)
            except BaseException:
                await self._clean_up_failed_connection(guild, channel)
                raise

    async def _reconcile(self, member, after) -> None:
        guild = member.guild
        voice_client = guild.voice_client

        if voice_client is not None:
            current_channel = getattr(voice_client, "channel", None)
            if current_channel is not None and human_member_count(current_channel) > 0:
                return

            channel_name = str(current_channel) if current_channel is not None else "voice"
            try:
                # force=True also removes a half-open client left by a failed handshake.
                await voice_client.disconnect(force=True)
                self.logger.info(
                    "Disconnected from %s because I was alone in it.", channel_name
                )
            except Exception:
                self.logger.exception("Failed to disconnect from %s", channel_name)
                return

        target = after.channel
        if target is None:
            return

        # The event may have waited behind another handshake. Re-read live state so
        # an old join event cannot reconnect after its member has already left.
        member_channel = getattr(getattr(member, "voice", None), "channel", None)
        if member_channel != target or human_member_count(target) == 0:
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
            return
        except Exception:
            self.logger.exception("Could not connect to %s", target)
            await self._clean_up_failed_connection(guild, target)
            return

        # A leave event can arrive while connect() is awaiting Discord. Do not
        # leave the bot parked alone until another event happens to clean it up.
        if human_member_count(target) == 0:
            await client.disconnect(force=True)
            self.logger.info(
                "Disconnected from %s because I was alone in it.", target
            )
            return

        self.logger.info("Connected to %s because someone joined it.", target)

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
