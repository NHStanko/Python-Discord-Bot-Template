import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from helpers.voice_connection import VoiceConnectionManager


class FakeChannel:
    def __init__(self, name: str, guild) -> None:
        self.name = name
        self.guild = guild
        self.members = []
        self.connect_started = asyncio.Event()
        self.finish_connect = asyncio.Event()
        self.client = SimpleNamespace(channel=self, disconnect=AsyncMock(), is_connected=Mock(return_value=True))

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


def recovery_fixture():
    guild = SimpleNamespace(id=1, voice_client=None, unavailable=False)
    channel = FakeChannel("General", guild)
    guild.voice_channels = [channel]
    channel.members.append(
        SimpleNamespace(bot=False, guild=guild, voice=SimpleNamespace(channel=channel))
    )
    channel.finish_connect.set()
    return VoiceConnectionManager(logging.getLogger("test")), guild, channel


def test_recovers_without_a_human_voice_event():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        await manager.reconcile_guild(guild)
        guild.voice_client = None  # Library cleaned up a dropped connection.
        channel.connect_started.clear()
        await manager.reconcile_guild(guild)
        assert channel.connect_started.is_set()
        assert guild.voice_client is channel.client

    asyncio.run(exercise())


def test_replaces_unhealthy_client_even_when_humans_remain():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        guild.voice_client = channel.client
        channel.client.is_connected.return_value = False
        await manager.reconcile_guild(guild)
        channel.client.disconnect.assert_awaited_once_with(force=True)
        assert channel.connect_started.is_set()

    asyncio.run(exercise())


def test_recovery_backs_off_and_human_events_cannot_bypass_it(monkeypatch):
    async def exercise():
        manager, guild, channel = recovery_fixture()
        now = 1000.0
        monkeypatch.setattr("helpers.voice_connection.time.monotonic", lambda: now)
        connect = channel.connect
        channel.connect = AsyncMock(side_effect=TimeoutError)
        for delay in (30, 60, 120, 240, 300, 300):
            previous = channel.connect.await_count
            await manager.reconcile_guild(guild)
            assert channel.connect.await_count == previous + 1
            now += delay - 1
            await manager.reconcile_guild(guild)
            await manager.handle_voice_state_update(
                channel.members[0], SimpleNamespace(channel=channel)
            )
            assert channel.connect.await_count == previous + 1
            now += 1
        channel.connect = connect
        await manager.reconcile_guild(guild)
        assert guild.voice_client is channel.client
        assert guild.id not in manager._retry_after

    asyncio.run(exercise())


def test_recovery_does_not_join_empty_bot_only_or_unavailable_channels():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        guild.unavailable = True
        await manager.reconcile_guild(guild)
        guild.unavailable = False
        channel.members.clear()
        await manager.reconcile_guild(guild)
        channel.members.append(SimpleNamespace(bot=True))
        await manager.reconcile_guild(guild)
        assert not channel.connect_started.is_set()

    asyncio.run(exercise())


def test_recovery_and_join_share_handshake_lock():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        channel.finish_connect.clear()
        channel.connect = AsyncMock(wraps=channel.connect)
        recovery = asyncio.create_task(manager.reconcile_guild(guild))
        await channel.connect_started.wait()
        join = asyncio.create_task(manager.handle_voice_state_update(
            channel.members[0], SimpleNamespace(channel=channel)
        ))
        channel.finish_connect.set()
        await asyncio.gather(recovery, join)
        channel.connect.assert_awaited_once()

    asyncio.run(exercise())


def test_cancelling_recovery_cleans_up_handshake():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        channel.finish_connect.clear()
        recovery = asyncio.create_task(manager.reconcile_guild(guild))
        await channel.connect_started.wait()
        recovery.cancel()
        await asyncio.gather(recovery, return_exceptions=True)
        assert guild.voice_client is None
        channel.client.disconnect.assert_awaited_once_with(force=True)

    asyncio.run(exercise())


def test_recovery_preserves_healthy_occupied_channel():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        other = FakeChannel("Gaming", guild)
        other.members.append(SimpleNamespace(bot=False))
        guild.voice_channels.insert(0, other)
        guild.voice_client = channel.client
        await manager.reconcile_guild(guild)
        channel.client.disconnect.assert_not_awaited()
        assert not channel.connect_started.is_set()
        assert not other.connect_started.is_set()

    asyncio.run(exercise())


def test_manual_connect_replaces_stale_client():
    async def exercise():
        manager, guild, channel = recovery_fixture()
        guild.voice_client = channel.client
        channel.client.is_connected.return_value = False
        assert await manager.connect(channel) is channel.client
        channel.client.disconnect.assert_awaited_once_with(force=True)
        assert channel.connect_started.is_set()

    asyncio.run(exercise())
