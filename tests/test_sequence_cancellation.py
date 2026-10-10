import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from helpers.tts_service import ChatterboxTTSService
from helpers.voice_store import VoiceStore


def test_cancelled_sequence_stops_process_before_removing_output(tmp_path, monkeypatch):
    async def exercise():
        store = VoiceStore(tmp_path)
        service = ChatterboxTTSService(store)
        started = asyncio.Event()
        reaped = False

        async def communicate():
            nonlocal reaped
            if not started.is_set():
                started.set()
                await asyncio.Future()
            assert list(store.generated_dir.glob("*.wav"))
            reaped = True
            return b"", b""

        process = SimpleNamespace(
            returncode=None, communicate=AsyncMock(side_effect=communicate), kill=Mock()
        )
        monkeypatch.setattr(
            "helpers.tts_service.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        )
        task = asyncio.create_task(service.combine_sequence([(None, 1.0)]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        process.kill.assert_called_once()
        assert reaped
        assert not list(store.generated_dir.iterdir())

    asyncio.run(exercise())


def test_failed_sequence_removes_output(tmp_path, monkeypatch):
    service = ChatterboxTTSService(VoiceStore(tmp_path))
    process = SimpleNamespace(
        returncode=1, communicate=AsyncMock(return_value=(b"", b"invalid audio"))
    )
    monkeypatch.setattr(
        "helpers.tts_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    with pytest.raises(ValueError, match="invalid audio"):
        asyncio.run(service.combine_sequence([(None, 1.0)]))
    assert not list(service.store.generated_dir.iterdir())
