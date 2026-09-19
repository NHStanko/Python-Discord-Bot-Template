import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from helpers.ai import AIHelper, close_ai_helpers, load_ai_helper_from_config
from helpers.http_client import close_http_session, get_http_session
from helpers.reddit import _get_reddit_client, close_reddit_client


@pytest.fixture
def immediate_to_thread(monkeypatch: pytest.MonkeyPatch):
    async def run_immediately(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("helpers.ai.asyncio.to_thread", run_immediately)


class FakeTransport:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeGeminiFile:
    name = "files/test-image"
    uri = "https://example.test/files/test-image"
    mime_type = "image/png"


class FakeGeminiFiles:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def upload(self, *, file):
        return FakeGeminiFile()

    def delete(self, *, name):
        self.deleted.append(name)


class FakeGeminiModels:
    def generate_content(self, **kwargs):
        return SimpleNamespace(text="generated text")


class FakeGeminiClient:
    def __init__(self) -> None:
        self.files = FakeGeminiFiles()
        self.models = FakeGeminiModels()
        self._api_client = SimpleNamespace(_httpx_client=FakeTransport())


def test_ai_http_session_is_reused_and_closed(
    monkeypatch: pytest.MonkeyPatch, immediate_to_thread
) -> None:
    client = FakeGeminiClient()
    monkeypatch.setattr("helpers.ai.genai.Client", lambda *, api_key: client)
    session = SimpleNamespace(closed=False, close_calls=0)

    async def close_session() -> None:
        session.close_calls += 1
        session.closed = True

    session.close = close_session
    monkeypatch.setattr("helpers.ai.aiohttp.ClientSession", lambda: session)

    async def exercise() -> None:
        helper = AIHelper(SimpleNamespace(), "key")
        assert await helper._get_http_session() is session
        assert await helper._get_http_session() is session
        await helper.close()

    asyncio.run(exercise())

    assert session.close_calls == 1
    assert client._api_client._httpx_client.close_calls == 1


def test_shared_http_session_is_reused_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(closed=False, close=AsyncMock())
    monkeypatch.setattr("helpers.http_client.aiohttp.ClientSession", lambda: session)
    owner = SimpleNamespace()

    async def exercise() -> None:
        assert await get_http_session(owner) is await get_http_session(owner)
        await close_http_session(owner)

    asyncio.run(exercise())
    session.close.assert_awaited_once()
    assert owner._shared_http_session is None


def test_gemini_uploaded_image_is_deleted_after_generation(
    monkeypatch: pytest.MonkeyPatch, immediate_to_thread
) -> None:
    client = FakeGeminiClient()
    monkeypatch.setattr("helpers.ai.genai.Client", lambda *, api_key: client)

    async def exercise() -> tuple[str | None, str | None]:
        helper = AIHelper(SimpleNamespace(), "key")
        return await helper.generate_content("describe", image_path="image.png")

    assert asyncio.run(exercise()) == ("generated text", None)
    assert client.files.deleted == ["files/test-image"]


def test_ai_helper_is_cached_per_bot_and_closed(
    monkeypatch, tmp_path, immediate_to_thread
) -> None:
    clients: list[FakeGeminiClient] = []

    def make_client(*, api_key):
        client = FakeGeminiClient()
        clients.append(client)
        return client

    monkeypatch.setattr("helpers.ai.genai.Client", make_client)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"gemini_api_key": "key", "gemini_model": "model"}),
        encoding="utf-8",
    )
    bot = SimpleNamespace()

    first = load_ai_helper_from_config(bot, str(config_path))
    second = load_ai_helper_from_config(bot, str(config_path))

    assert first is second
    assert len(clients) == 1
    asyncio.run(close_ai_helpers(bot))
    assert not bot._ai_helper_cache
    assert clients[0]._api_client._httpx_client.close_calls == 1


def test_reddit_client_is_reused_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    clients = []

    class FakeReddit:
        def __init__(self, **kwargs):
            self.close_calls = 0
            clients.append(self)

        async def close(self) -> None:
            self.close_calls += 1

    monkeypatch.setattr("helpers.reddit.asyncpraw.Reddit", FakeReddit)
    bot = SimpleNamespace(
        config={
            "reddit_client_id": "id",
            "reddit_client_secret": "secret",
            "reddit_user_agent": "agent",
        }
    )

    async def exercise() -> None:
        results = await asyncio.gather(*(_get_reddit_client(bot) for _ in range(5)))
        assert all(client is results[0] for client in results)
        await close_reddit_client(bot)

    asyncio.run(exercise())

    assert len(clients) == 1
    assert clients[0].close_calls == 1
    assert bot._reddit_client is None
