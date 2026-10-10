import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


@pytest.mark.parametrize("already_exited", [False, True])
def test_ffmpeg_cancellation_reaps_process_and_propagates(already_exited: bool) -> None:
    async def scenario() -> None:
        communicating = asyncio.Event()

        async def communicate():
            if not communicating.is_set():
                communicating.set()
                await asyncio.Future()
            return b"", b""

        process = SimpleNamespace(
            communicate=AsyncMock(side_effect=communicate),
            kill=Mock(),
            returncode=0 if already_exited else None,
        )
        with patch(
            "cogs.voice.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            task = asyncio.create_task(run_ffmpeg(["-i", "input.wav", "output.mp3"]))
            await communicating.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert process.communicate.await_count == 2
        assert process.kill.call_count == (0 if already_exited else 1)

    asyncio.run(scenario())


def test_sound_editor_rejects_other_users() -> None:
    response = SimpleNamespace(send_message=AsyncMock())
    interaction = SimpleNamespace(user=SimpleNamespace(id=2), response=response)
    view = SimpleNamespace(authorized_user_id=1)

    allowed = asyncio.run(SoundModifyView.interaction_check(view, interaction))

    assert not allowed
    response.send_message.assert_awaited_once()


def test_sound_editor_buttons_acknowledge_interactions(monkeypatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(
            "cogs.voice.get_sound_with_extension",
            lambda **kwargs: {"airhorn": "airhorn.mp3"},
        )
        monkeypatch.setattr("cogs.voice.get_sound", lambda **kwargs: ["airhorn"])
        monkeypatch.setattr("cogs.voice.shutil.copy", Mock())
        view = SoundModifyView("airhorn", authorized_user_id=1)
        volume_calls = []
        for button in view.children:
            events = []

            async def apply_volume(factor):
                events.append("convert")
                volume_calls.append(factor)

            monkeypatch.setattr(view, "_apply_volume", apply_volume)
            message = SimpleNamespace(delete=AsyncMock())
            response = SimpleNamespace(
                defer=AsyncMock(side_effect=lambda **kwargs: events.append("defer")),
                edit_message=AsyncMock(
                    side_effect=lambda **kwargs: events.append("edit_message")
                ),
            )
            followup = SimpleNamespace(
                send=AsyncMock(
                    side_effect=lambda *args, **kwargs: (
                        events.append("followup"),
                        message,
                    )[1]
                )
            )
            interaction = SimpleNamespace(
                response=response,
                followup=followup,
                edit_original_response=AsyncMock(
                    side_effect=lambda **kwargs: events.append("edit_original")
                ),
            )
            monkeypatch.setattr(
                view,
                "_reset_sound",
                AsyncMock(side_effect=lambda: events.append("copy")),
            )
            await button.callback(interaction)

            if button.label.startswith("Vol"):
                assert events == ["defer", "convert", "followup"]
                response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
                message.delete.assert_awaited_once_with(delay=5)
            elif button.label == "Reset":
                assert events == ["defer", "copy", "edit_original"]
                response.defer.assert_awaited_once_with(ephemeral=True)
            else:
                assert events == ["edit_message"]
                response.edit_message.assert_awaited_once()

        assert volume_calls == [0.8, 1.2]

    asyncio.run(scenario())


def test_sound_editor_reports_volume_and_reset_failures(monkeypatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(
            "cogs.voice.get_sound_with_extension",
            lambda **kwargs: {"airhorn": "airhorn.mp3"},
        )
        monkeypatch.setattr("cogs.voice.get_sound", lambda **kwargs: ["airhorn"])
        monkeypatch.setattr("cogs.voice.shutil.copy", Mock())
        view = SoundModifyView("airhorn", authorized_user_id=1)

        async def fail_volume(factor):
            raise RuntimeError("conversion failed")

        monkeypatch.setattr(view, "_apply_volume", fail_volume)
        buttons = {button.label: button for button in view.children}
        for label in ("Vol Up", "Vol Down", "Reset"):
            events = []
            response = SimpleNamespace(
                defer=AsyncMock(side_effect=lambda **kwargs: events.append("defer")),
                edit_message=AsyncMock(),
            )
            followup = SimpleNamespace(
                send=AsyncMock(
                    side_effect=lambda *args, **kwargs: events.append("error")
                )
            )
            interaction = SimpleNamespace(
                response=response,
                followup=followup,
                edit_original_response=AsyncMock(
                    side_effect=lambda **kwargs: events.append("edit_original")
                ),
            )
            if label == "Reset":
                monkeypatch.setattr(
                    view,
                    "_reset_sound",
                    AsyncMock(side_effect=RuntimeError("copy failed")),
                )
            await buttons[label].callback(interaction)
            assert events == ["defer", "error"]
            response.defer.assert_awaited_once()
            followup.send.assert_awaited_once()
            interaction.edit_original_response.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("second_operation", ["volume", "reset", "other_sound"])
def test_sound_edits_serialize_across_views(monkeypatch, tmp_path, second_operation):
    async def scenario():
        sound_dir = tmp_path / "sounds"
        sound_dir.mkdir()
        original_dir = sound_dir / "original"
        original_dir.mkdir()
        for name in ("airhorn", "bell"):
            (sound_dir / f"{name}.mp3").write_text("100")
            (original_dir / f"{name}.mp3").write_text("100")
        monkeypatch.setattr("cogs.voice.SOUNDS_DIR", sound_dir)
        monkeypatch.setattr("cogs.voice.SOUNDS_TEMP_DIR", sound_dir / "temp")
        monkeypatch.setattr("cogs.voice.SOUNDS_ORIGINAL_DIR", original_dir)
        monkeypatch.setattr(
            "cogs.voice.get_sound_with_extension",
            lambda **kwargs: {"airhorn": "airhorn.mp3", "bell": "bell.mp3"},
        )
        monkeypatch.setattr(
            "cogs.voice.get_sound", lambda **kwargs: ["airhorn", "bell"]
        )
        first = SoundModifyView("airhorn", 1)
        second = SoundModifyView(
            "bell" if second_operation == "other_sound" else "airhorn", 2
        )
        started = asyncio.Event()
        release = asyncio.Event()
        second_started = asyncio.Event()
        calls = []

        async def convert(arguments):
            source = Path(arguments[2])
            value = float(source.read_text())
            calls.append(source.name)
            if len(calls) == 1:
                started.set()
                await release.wait()
            else:
                second_started.set()
            Path(arguments[-1]).write_text(
                str(value * float(arguments[4].split("=")[1]))
            )

        monkeypatch.setattr("cogs.voice.run_ffmpeg", convert)
        first_task = asyncio.create_task(first._apply_volume(1.2))
        await started.wait()
        second_task = asyncio.create_task(
            second._reset_sound()
            if second_operation == "reset"
            else second._apply_volume(0.8)
        )
        await asyncio.sleep(0)
        if second_operation == "other_sound":
            await second_started.wait()
        else:
            assert not second_task.done()
            assert calls == ["airhorn.mp3"]
        assert (sound_dir / "airhorn.mp3").read_text() == "100"
        release.set()
        await asyncio.gather(first_task, second_task)
        expected = {"volume": 96, "reset": 100, "other_sound": 120}[second_operation]
        assert float((sound_dir / "airhorn.mp3").read_text()) == pytest.approx(expected)
        if second_operation == "other_sound":
            assert float((sound_dir / "bell.mp3").read_text()) == 80
        assert list((sound_dir / "temp").iterdir()) == []

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_sound_edit_releases_lock_after_failed_conversion(
    monkeypatch, tmp_path, cancel
):
    async def scenario():
        from cogs.voice import sound_edit_lock

        source = tmp_path / "sound.mp3"
        source.write_text("original")
        monkeypatch.setattr("cogs.voice.SOUNDS_DIR", tmp_path)
        monkeypatch.setattr("cogs.voice.SOUNDS_TEMP_DIR", tmp_path / "temp")
        view = SimpleNamespace(sound_ext="sound.mp3")
        started = asyncio.Event()

        async def fail(arguments):
            started.set()
            if cancel:
                await asyncio.Future()
            raise RuntimeError("conversion failed")

        monkeypatch.setattr("cogs.voice.run_ffmpeg", fail)
        lock = sound_edit_lock(source)
        task = asyncio.create_task(SoundModifyView._apply_volume(view, 1.2))
        await started.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
            await task
        assert not lock.locked()
        assert source.read_text() == "original"
        assert list((tmp_path / "temp").iterdir()) == []

    asyncio.run(scenario())


def test_cancelled_reset_finishes_copy_before_unlocking(monkeypatch, tmp_path):
    async def scenario():
        from cogs.voice import sound_edit_lock

        source = tmp_path / "sound.mp3"
        source.write_text("modified")
        monkeypatch.setattr("cogs.voice.SOUNDS_DIR", tmp_path)
        monkeypatch.setattr("cogs.voice.SOUNDS_TEMP_DIR", tmp_path / "temp")
        started = asyncio.Event()
        release = asyncio.Event()

        async def worker(function, original, destination):
            started.set()
            await release.wait()
            destination.write_text("original")

        monkeypatch.setattr("cogs.voice.asyncio.to_thread", worker)
        view = SimpleNamespace(sound_ext="sound.mp3")
        lock = sound_edit_lock(source)
        task = asyncio.create_task(SoundModifyView._reset_sound(view))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert lock.locked()
        assert not task.done()
        assert source.read_text() == "modified"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not lock.locked()
        assert source.read_text() == "modified"
        assert list((tmp_path / "temp").iterdir()) == []

    asyncio.run(scenario())
