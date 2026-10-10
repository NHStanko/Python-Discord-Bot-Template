import asyncio
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from helpers.ai import AIHelper


@pytest.mark.parametrize("write_fails", [False, True])
def test_download_cleans_partial_file_on_write_failure(
    tmp_path, monkeypatch, write_fails
):
    mkstemp = tempfile.mkstemp
    monkeypatch.setattr(
        "helpers.ai.tempfile.mkstemp", lambda **kw: mkstemp(dir=tmp_path, **kw)
    )
    if write_fails:
        write_bytes = Path.write_bytes

        def fail(path, content):
            write_bytes(path, content[:2])
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_bytes", fail)

    data = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(data, format="PNG")
    image_content = data.getvalue()

    class Response:
        status = 200
        content_length = None
        headers = {"Content-Type": "image/png"}

        @property
        def content(self):
            return self

        async def iter_chunked(self, size):
            yield image_content

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("helpers.ai.genai.Client", lambda **kwargs: SimpleNamespace())
    helper = AIHelper(SimpleNamespace(), "test")
    helper._get_http_session = AsyncMock(
        return_value=SimpleNamespace(get=lambda *a, **kw: Response())
    )
    result = asyncio.run(helper.download_image("https://example.test/image.png"))
    if write_fails:
        assert result is None
        assert not list(tmp_path.iterdir())
    else:
        assert Path(result).read_bytes() == image_content
        Path(result).unlink()


def test_cancelled_image_save_waits_for_writer_and_removes_file(tmp_path, monkeypatch):
    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()
        output = tmp_path / "image.png"

        async def writer(*args):
            started.set()
            await release.wait()
            output.write_bytes(b"image")
            return str(output)

        monkeypatch.setattr("helpers.ai.asyncio.to_thread", writer)
        helper = AIHelper.__new__(AIHelper)
        task = asyncio.create_task(helper._save_image(b"image"))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not output.exists()

    asyncio.run(exercise())
