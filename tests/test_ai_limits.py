import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from helpers.ai import AIHelper


@pytest.fixture
def helper_factory(monkeypatch):
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: None)
    )
    monkeypatch.setattr("helpers.ai.genai.Client", lambda **kwargs: client)

    def create(settings=None, bot=None):
        bot = bot or SimpleNamespace(config={"ai": settings or {}})
        return AIHelper(bot, "test")

    return create


def test_ai_limit_is_shared_and_slots_recover_after_failure(helper_factory):
    async def exercise():
        bot = SimpleNamespace(config={"ai": {"max_concurrent_requests": 2}})
        first, second = helper_factory(bot=bot), helper_factory(bot=bot)
        release = asyncio.Event()
        entered = 0
        ready = asyncio.Event()

        async def generate(*args, **kwargs):
            nonlocal entered
            entered += 1
            if entered == 2:
                ready.set()
            await release.wait()
            raise RuntimeError("upstream failed")

        first._sdk_call = second._sdk_call = generate
        tasks = [
            asyncio.create_task(helper.generate_content("test"))
            for helper in (first, second)
        ]
        await ready.wait()
        text, error = await second.generate_content("test")
        assert text is None
        assert "maximum simultaneous" in error
        assert entered == 2
        release.set()
        await asyncio.gather(*tasks)
        first._sdk_call = AsyncMock(return_value=SimpleNamespace(text="ok"))
        assert await first.generate_content("test") == ("ok", None)
        assert first._request_limiter.active == 0

    asyncio.run(exercise())


def test_sdk_cancellation_holds_slot_until_thread_finishes(helper_factory, monkeypatch):
    import threading

    async def exercise():
        helper = helper_factory({"max_concurrent_requests": 1})
        release = threading.Event()
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def generate(**kwargs):
            loop.call_soon_threadsafe(started.set)
            release.wait(5)
            return SimpleNamespace(text="ok")

        helper.client.models.generate_content = generate
        task = asyncio.create_task(helper.generate_content("test"))
        try:
            await started.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert helper._request_limiter.active == 1
            assert "maximum simultaneous" in (await helper.generate_content("test"))[1]
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert helper._request_limiter.active == 0

    asyncio.run(exercise())


def image_bytes():
    data = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(data, format="PNG")
    return data.getvalue()


class Response:
    status = 200

    def __init__(self, body, content_length=None, mime="image/png"):
        self.body = body
        self.content_length = content_length
        self.headers = {"Content-Type": mime}
        self.content = self
        self.chunks_read = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), 10):
            self.chunks_read += 1
            yield self.body[offset : offset + 10]


def download(helper, response):
    helper._get_http_session = AsyncMock(
        return_value=SimpleNamespace(get=lambda *a, **kw: response)
    )
    return asyncio.run(helper.download_image("https://example.test/image"))


def test_download_validates_actual_image_and_extension(helper_factory):
    body = image_bytes()
    path = download(helper_factory(), Response(body))
    assert path is not None
    try:
        assert Path(path).suffix == ".png"
        assert Path(path).read_bytes() == body
    finally:
        Path(path).unlink()


def test_download_bounds_stream_without_content_length(helper_factory):
    response = Response(image_bytes())
    assert download(helper_factory({"max_image_bytes": 15}), response) is None
    assert response.chunks_read == 2


def test_download_rejects_large_header_before_reading(helper_factory):
    response = Response(image_bytes(), content_length=1000)
    assert download(helper_factory({"max_image_bytes": 15}), response) is None
    assert response.chunks_read == 0


@pytest.mark.parametrize(
    "body,mime,pixels",
    [
        (b"not an image", "image/png", 100),
        (image_bytes(), "text/html", 100),
        (image_bytes(), "image/png", 4),
    ],
)
def test_download_rejects_invalid_or_oversized_images(
    helper_factory, body, mime, pixels
):
    assert (
        download(
            helper_factory({"max_image_pixels": pixels}), Response(body, mime=mime)
        )
        is None
    )
