import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import create_bot
from helpers import message_handler
from helpers.config import load_config, validate_config

CONFIG = {"prefix": "!", "token": "test-token", "sync_commands_globally": False}


def test_import_has_no_config_or_logging_io(tmp_path):
    # Fail if importing bot attempts to load local configuration or open log files.
    code = """
import builtins
import logging
original = builtins.open
def guarded(file, *args, **kwargs):
    if str(file).endswith(('config.json', '.log')):
        raise AssertionError('import-time I/O')
    return original(file, *args, **kwargs)
builtins.open = guarded
import bot
assert not logging.getLogger('discord_bot').handlers
assert not hasattr(bot, 'bot')
"""
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )


def test_config_validation_and_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**CONFIG, "owners": ["123"]}))
    config = load_config(path)
    assert config["owners"] == [123]
    assert config["ai"]["max_concurrent_requests"] == 32
    assert "ai" not in CONFIG
    assert (
        validate_config({**CONFIG, "ai": {"max_concurrent_requests": 100}})["ai"][
            "max_concurrent_requests"
        ]
        == 100
    )
    for values in (
        {"token": ""},
        {"prefix": 12},
        {"owners": [True]},
        {"ai": {"max_concurrent_requests": 0}},
        {"tts": []},
    ):
        with pytest.raises(ValueError):
            validate_config({**CONFIG, **values})


def test_setup_runs_in_current_loop_and_syncs_after_loading(monkeypatch):
    async def exercise():
        bot = create_bot({**CONFIG, "sync_commands_globally": True})
        events = []
        loop = asyncio.get_running_loop()

        async def record(name):
            assert asyncio.get_running_loop() is loop
            events.append(name)

        monkeypatch.setattr("bot.init_db", lambda: record("database"))
        monkeypatch.setattr(bot, "load_cogs", lambda: record("cogs"))
        monkeypatch.setattr(bot.tree, "sync", lambda: record("sync"))
        await bot.setup_hook()
        assert events == ["database", "cogs", "sync"]
        await bot.close()

    asyncio.run(exercise())


def test_failed_handler_does_not_stop_other_handlers_or_commands(monkeypatch, caplog):
    events = []

    async def failing(message):
        raise RuntimeError("handler failure")

    async def succeeding(message):
        events.append("handler")

    async def command(message):
        events.append("command")

    monkeypatch.setattr(message_handler, "_registry", [])
    message_handler.register_message_handler()(failing)
    message_handler.register_message_handler()(succeeding)

    async def exercise():
        bot = create_bot(CONFIG)
        bot.process_commands = command
        await bot.on_message(
            SimpleNamespace(author=SimpleNamespace(bot=False), content="!ping")
        )
        await bot.close()

    asyncio.run(exercise())
    assert events == ["handler", "command"]
    assert "handler failure" in caplog.text


def test_dispatch_failure_still_runs_commands(monkeypatch):
    async def exercise():
        bot = create_bot(CONFIG)
        bot.process_commands = AsyncMock()
        monkeypatch.setattr(
            "bot.process_message",
            AsyncMock(side_effect=RuntimeError("dispatcher failed")),
        )
        with pytest.raises(RuntimeError):
            await bot.on_message(
                SimpleNamespace(author=SimpleNamespace(bot=False), content="!ping")
            )
        bot.process_commands.assert_awaited_once()
        await bot.close()

    asyncio.run(exercise())


def test_thinkso_reload_does_not_duplicate_listeners():
    async def exercise():
        bot = create_bot(CONFIG)
        await bot.load_extension("cogs.thinkso")
        await bot.reload_extension("cogs.thinkso")
        assert len(bot.extra_events["on_message"]) == 1
        await bot.unload_extension("cogs.thinkso")
        assert not bot.extra_events["on_message"]
        await bot.close()

    asyncio.run(exercise())


def test_all_extensions_load_and_unload_without_connecting(tmp_path):
    # Extension unloading removes modules from sys.modules. Isolate it from tests
    # that imported cog classes during collection and later patch their globals.
    code = """
import asyncio
import os
import sys
from pathlib import Path
from bot import create_bot
from helpers import db_manager

async def main():
    db_manager.DATABASE_PATH = str(Path(sys.argv[1]) / 'test.db')
    os.environ['TTS_DATA_DIR'] = str(Path(sys.argv[1]) / 'tts')
    bot = create_bot({'token': 'test', 'prefix': '!', 'sync_commands_globally': False}, voice_enabled=True)
    try:
        await bot.setup_hook()
        expected = {f'cogs.{path.stem}' for path in Path('cogs').glob('*.py')}
        assert set(bot.extensions) == expected
    finally:
        await bot.close()
    assert not bot.extensions
asyncio.run(main())
"""
    subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
