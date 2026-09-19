import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from helpers.voice_connection import VoiceConnectionManager


class FakeChannel:
    def __init__(self, name: str, guild) -> None:
        self.name = name
        self.guild = guild
        self.members = []
        self.connect_started = asyncio.Event()
        self.finish_connect = asyncio.Event()
        self.client = SimpleNamespace(channel=self, disconnect=AsyncMock())

        async def disconnect(*, force=False):
            self.guild.voice_client = None

        self.client.disconnect.side_effect = disconnect

    def __str__(self) -> str:
        return self.name

    async def connect(self, *, reconnect=True):
        assert reconnect is False
        self.guild.voice_client = self.client
        self.connect_started.set()
        await self.finish_connect.wait()
        return self.client


def test_leave_during_handshake_is_serialized_and_disconnected() -> None:
    async def exercise() -> tuple[FakeChannel, object]:
        guild = SimpleNamespace(id=1, voice_client=None)
        channel = FakeChannel("General", guild)
        member = SimpleNamespace(bot=False, guild=guild)
        member.voice = SimpleNamespace(channel=channel)
        channel.members.append(member)
        manager = VoiceConnectionManager(logging.getLogger("test"))

        join = asyncio.create_task(
            manager.handle_voice_state_update(member, SimpleNamespace(channel=channel))
        )
        await channel.connect_started.wait()

        member.voice.channel = None
        channel.members.clear()
        leave = asyncio.create_task(
            manager.handle_voice_state_update(member, SimpleNamespace(channel=None))
        )
        channel.finish_connect.set()
        await asyncio.gather(join, leave)
        return channel, guild

    channel, guild = asyncio.run(exercise())

    channel.client.disconnect.assert_awaited_once_with(force=True)


def test_stale_join_event_does_not_connect_after_member_left() -> None:
    async def exercise() -> FakeChannel:
        guild = SimpleNamespace(id=1, voice_client=None)
        channel = FakeChannel("General", guild)
        member = SimpleNamespace(
            bot=False, guild=guild, voice=SimpleNamespace(channel=None)
        )
        manager = VoiceConnectionManager(logging.getLogger("test"))

        await manager.handle_voice_state_update(
            member, SimpleNamespace(channel=channel)
        )
        return channel

    channel = asyncio.run(exercise())

    assert not channel.connect_started.is_set()


def test_automatic_connect_timeout_is_handled_and_cleaned_up() -> None:
    async def exercise() -> FakeChannel:
        guild = SimpleNamespace(id=1, voice_client=None)
        channel = FakeChannel("General", guild)
        member = SimpleNamespace(
            bot=False, guild=guild, voice=SimpleNamespace(channel=channel)
        )
        channel.members.append(member)
        manager = VoiceConnectionManager(logging.getLogger("test"))

        async def time_out(*, reconnect=True):
            assert reconnect is False
            guild.voice_client = channel.client
            raise TimeoutError

        channel.connect = time_out
        await manager.handle_voice_state_update(
            member, SimpleNamespace(channel=channel)
        )
        return channel

    channel = asyncio.run(exercise())

    channel.client.disconnect.assert_awaited_once_with(force=True)
    assert channel.guild.voice_client is None
