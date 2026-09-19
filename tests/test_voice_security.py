import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cogs.voice import (
    SoundModifyView,
    conversion_ffmpeg_args,
    run_ffmpeg,
    validate_sound_name,
    validate_time_range,
    validate_youtube_url,
)


@pytest.mark.parametrize(
    "name",
    ["../escape", "name; touch owned", "$(touch owned)", "/absolute", ""],
)
def test_sound_names_reject_shell_and_path_syntax(name: str) -> None:
    with pytest.raises(ValueError):
        validate_sound_name(name)


def test_sound_name_accepts_a_safe_filename() -> None:
    assert validate_sound_name("air horn-2") == "air horn-2"


@pytest.mark.parametrize(
    "url",
    [
        "http://youtube.com/watch?v=abc",
        "https://youtube.com.evil.example/watch?v=abc",
        "https://evil.example/?next=youtube.com",
        "file:///etc/passwd",
    ],
)
def test_youtube_urls_require_https_and_an_exact_host(url: str) -> None:
    with pytest.raises(ValueError):
        validate_youtube_url(url)


def test_youtube_short_url_is_allowed() -> None:
    assert validate_youtube_url("https://youtu.be/abc") == "https://youtu.be/abc"


def test_ffmpeg_command_is_an_argument_vector_with_bounded_duration() -> None:
    args = conversion_ffmpeg_args(
        Path("source;not-shell.wav"), Path("output file.mp3"), 4, 30
    )

    assert args == [
        "-y",
        "-ss",
        "4",
        "-i",
        "source;not-shell.wav",
        "-t",
        "30",
        "-vn",
        "output file.mp3",
    ]
    with pytest.raises(ValueError):
        validate_time_range(0, -1)
    with pytest.raises(ValueError):
        validate_time_range(0, 31)


def test_ffmpeg_runner_never_invokes_a_shell() -> None:
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"")),
        returncode=0,
    )
    create_process = AsyncMock(return_value=process)

    with patch("cogs.voice.asyncio.create_subprocess_exec", create_process):
        asyncio.run(run_ffmpeg(["-i", "input;still-data.wav", "output.mp3"]))

    create_process.assert_awaited_once()
    assert create_process.await_args.args[:4] == (
        "ffmpeg",
        "-i",
        "input;still-data.wav",
        "output.mp3",
    )


def test_sound_editor_rejects_other_users() -> None:
    response = SimpleNamespace(send_message=AsyncMock())
    interaction = SimpleNamespace(user=SimpleNamespace(id=2), response=response)
    view = SimpleNamespace(authorized_user_id=1)

    allowed = asyncio.run(SoundModifyView.interaction_check(view, interaction))

    assert not allowed
    response.send_message.assert_awaited_once()
