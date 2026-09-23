import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from helpers.ai import AIHelper, close_ai_helpers, load_ai_helper_from_config
from helpers.http_client import close_http_session, get_http_session
from helpers.reddit import _get_reddit_client, close_reddit_client


def helper(**kwargs):
    return AIHelper(SimpleNamespace(), "key", "test-model", **kwargs)


def test_ai_http_session_is_reused_and_closed(monkeypatch):
    session = SimpleNamespace(closed=False, close=AsyncMock())
    monkeypatch.setattr("helpers.ai.aiohttp.ClientSession", lambda: session)

    async def exercise():
        ai = helper()
        assert await ai._get_http_session() is await ai._get_http_session()
        await ai.close()
        await ai.close()

    asyncio.run(exercise())
    session.close.assert_awaited_once()


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



@pytest.mark.parametrize("base_url,endpoint", [
    ("https://openrouter.ai/api/v1", "chat/completions"),
    ("https://api.openai.com/v1", "responses"),
])
def test_search_routes_and_separate_model(base_url, endpoint):
    ai = helper(base_url=base_url, search_model="search-model")
    response = (
        {"output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]}
        if endpoint == "responses" else
        {"choices": [{"message": {"content": "answer"}}]}
    )
    ai._post = AsyncMock(return_value=(response, None))
    assert asyncio.run(ai.generate_content("research", enable_web_search=True)) == ("answer", None)
    route, payload = ai._post.call_args.args
    assert route == endpoint
    assert payload["model"] == "search-model"
    if endpoint == "responses":
        assert payload["tools"] == [{"type": "web_search"}]
    else:
        assert payload["plugins"] == [{"id": "web"}]


def test_image_is_encoded_and_strict_schema_preserved(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (2, 2)).save(path)
    ai = helper()
    ai._post = AsyncMock(return_value=({"choices": [{"message": {"content": "{}"}}]}, None))
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    assert asyncio.run(ai.generate_content(
        "describe", image_path=str(path), response_schema=schema,
    )) == ("{}", None)
    payload = ai._post.call_args.args[1]
    image = payload["messages"][1]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")
    assert payload["response_format"]["json_schema"]["schema"] == schema
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in payload


@pytest.mark.parametrize("mode,expected", [
    ("json_schema", "json_schema"), ("json_object", "json_object"), ("prompt", None),
])
def test_structured_output_modes(mode, expected):
    ai = helper(structured_output=mode, reasoning_effort="high")
    ai._post = AsyncMock(return_value=({"choices": [{"message": {"content": "{}"}}]}, None))
    asyncio.run(ai.generate_content("JSON", response_schema={"type": "object"}))
    payload = ai._post.call_args.args[1]
    assert payload.get("response_format", {}).get("type") == expected
    assert payload["reasoning_effort"] == "high"
    assert "Required JSON schema" in payload["messages"][0]["content"]


def test_custom_endpoint_requires_explicit_search_choice():
    ai = helper(base_url="https://example.test/v1")
    ai._post = AsyncMock()
    text, error = asyncio.run(ai.generate_content("research", enable_web_search=True))
    assert text is None and "not configured" in error
    ai._post.assert_not_awaited()


def test_search_can_be_explicitly_disabled():
    ai = helper(web_search="off")
    ai._post = AsyncMock(return_value=({"choices": [{"message": {"content": "text"}}]}, None))
    assert asyncio.run(ai.generate_content("question", enable_web_search=True)) == ("text", None)
    assert "plugins" not in ai._post.call_args.args[1]


@pytest.mark.parametrize("choice,expected", [
    ({"message": {"refusal": "no"}}, "declined"),
    ({"message": {"content": ""}}, "empty"),
    ({"message": {"content": "partial"}, "finish_reason": "length"}, "cut off"),
])
def test_unsuccessful_generation_is_reported(choice, expected):
    ai = helper()
    ai._post = AsyncMock(return_value=({"choices": [choice]}, None))
    text, error = asyncio.run(ai.generate_content("question"))
    assert text is None and expected in error


@pytest.mark.parametrize("status,expected", [(400, "rejected"), (401, "authentication"), (429, "quota"), (500, "failed")])
def test_http_errors_do_not_leak_provider_body(status, expected):
    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    response = Response()
    response.status = status
    session = SimpleNamespace(post=lambda *args, **kwargs: response)
    ai = helper()
    ai._get_http_session = AsyncMock(return_value=session)
    text, error = asyncio.run(ai.generate_content("private prompt"))
    assert text is None and expected in error
    assert "private prompt" not in error


def test_unreadable_image_does_not_silently_become_text_only():
    ai = helper()
    ai._post = AsyncMock()
    text, error = asyncio.run(ai.generate_content("describe", image_path="/missing/image.png"))
    assert text is None and "image" in error
    ai._post.assert_not_awaited()


def test_ai_helper_is_cached_per_configuration_and_closed(tmp_path):
    config_path = tmp_path / "config.json"
    config = {"ai_api_key": "key", "ai_model": "model"}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    bot = SimpleNamespace()
    first = load_ai_helper_from_config(bot, str(config_path))
    assert first is load_ai_helper_from_config(bot, str(config_path))
    config["ai_base_url"] = "https://api.openai.com/v1"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    second = load_ai_helper_from_config(bot, str(config_path))
    assert second is not first
    first.close = AsyncMock()
    second.close = AsyncMock()
    asyncio.run(close_ai_helpers(bot))
    first.close.assert_awaited_once()
    second.close.assert_awaited_once()
    assert not bot._ai_helper_cache


def test_environment_key_and_missing_model(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "environment-key")
    bot = SimpleNamespace(config={"ai_model": "model"})
    assert load_ai_helper_from_config(bot).api_key == "environment-key"
    bot.config = {}
    assert load_ai_helper_from_config(bot) is None


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
