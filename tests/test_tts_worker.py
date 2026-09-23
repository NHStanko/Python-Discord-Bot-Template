import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.tts import TTS
from helpers.tts_service import ChatterboxTTSService
from helpers.voice_store import VoiceStore


def test_worker_reuses_process_and_preserves_parent_outputs(tmp_path):
    store = VoiceStore(tmp_path)
    store.create_voice("first", 1)
    store.create_voice("second", 1)
    playing = store.generated_dir / "playing.wav"
    playing.write_bytes(b"playing")
    service = ChatterboxTTSService(store)

    async def exercise():
        try:
            await service.delete("first")
            worker = service._worker
            assert worker.pid != os.getpid()
            assert playing.read_bytes() == b"playing"
            with pytest.raises(ValueError, match="Unknown TTS job"):
                async with service._lock:
                    await service._run_model_job("invalid")
            await service.delete("second")
            assert service._worker is worker
            assert store.list_voices() == []
        finally:
            await service.close()
        assert worker.returncode is not None
        await service.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("shutdown", [False, True])
def test_blocked_model_does_not_block_bot_and_cancel_stops_worker(tmp_path, monkeypatch, shutdown):
    service = ChatterboxTTSService(VoiceStore(tmp_path))
    original_spawn = asyncio.create_subprocess_exec
    workers = []

    async def slow_worker(*args, **kwargs):
        worker = await original_spawn(
            sys.executable, "-c",
            "import sys, time; sys.stdin.readline(); time.sleep(30)",
            **kwargs,
        )
        workers.append(worker)
        return worker

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_worker)

    async def exercise():
        task = asyncio.create_task(service.synthesize("test", "hello"))
        try:
            # The bot's event loop must continue ticking during a blocked job.
            for _ in range(20):
                await asyncio.sleep(0.01)
                if workers:
                    break
            assert workers and service.busy and not task.done()
            await asyncio.sleep(0.02)
            assert not task.done()
        finally:
            if shutdown:
                await service.close()
                with pytest.raises(RuntimeError, match="worker stopped"):
                    await task
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            await service.close()
        assert workers[0].returncode is not None
        assert not service.busy
        assert list(service.store.generated_dir.iterdir()) == []

    asyncio.run(exercise())


def test_busy_retrain_responds_without_queueing_another_job():
    cog = TTS.__new__(TTS)
    cog.tts = SimpleNamespace(busy=True, train=AsyncMock())
    cog.require_owner = AsyncMock(return_value=True)
    interaction = SimpleNamespace(response=SimpleNamespace(
        send_message=AsyncMock(), defer=AsyncMock(),
    ))
    asyncio.run(TTS.retrain.callback(cog, interaction, "voice"))
    interaction.response.send_message.assert_awaited_once()
    assert "busy" in interaction.response.send_message.call_args.args[0]
    interaction.response.defer.assert_not_awaited()
    cog.tts.train.assert_not_awaited()


def test_voice_autocomplete_remains_available_while_model_is_busy(tmp_path):
    cog = TTS.__new__(TTS)
    cog.store = VoiceStore(tmp_path)
    cog.store.create_voice("Nick Calm", 1)
    cog.tts = SimpleNamespace(busy=True)
    choices = asyncio.run(cog.voice_autocomplete(None, "calm"))
    assert [(choice.name, choice.value) for choice in choices] == [("Nick Calm", "nick-calm")]


def test_autocomplete_bounds_slow_database_lookup(monkeypatch):
    cog = TTS.__new__(TTS)
    cog.store = SimpleNamespace(list_voices=lambda: [], list_samples=lambda _: [])

    async def timeout(awaitable, *, timeout):
        assert timeout == 1.0
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", timeout)
    assert asyncio.run(cog.voice_autocomplete(None, "")) == []
    interaction = SimpleNamespace(namespace=SimpleNamespace(voice="test"))
    assert asyncio.run(cog.sample_autocomplete(interaction, "")) == []


def test_cog_unload_closes_worker():
    cog = TTS.__new__(TTS)
    cog.tts = SimpleNamespace(close=AsyncMock())
    asyncio.run(cog.cog_unload())
    cog.tts.close.assert_awaited_once()


def test_delete_acknowledges_before_worker_job():
    cog = TTS.__new__(TTS)
    cog.store = SimpleNamespace(normalize_name=lambda name: name)
    cog.require_owner = AsyncMock(return_value=True)
    cog.schedule_original_response_deletion = lambda interaction: None
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )

    async def delete(name):
        interaction.response.defer.assert_awaited_once()

    cog.tts = SimpleNamespace(busy=False, delete=delete)
    asyncio.run(TTS.delete.callback(cog, interaction, "voice", True))
    interaction.edit_original_response.assert_awaited_once()
    assert "Permanently deleted" in interaction.edit_original_response.call_args.kwargs["content"]
