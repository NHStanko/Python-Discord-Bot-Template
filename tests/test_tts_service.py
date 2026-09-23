import shutil
import wave
from pathlib import Path

import pytest
import yt_dlp

from helpers.tts_service import PocketTTSService


def _silent_wav(path: Path, sample_rate: int, channels: int, seconds: float) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\0\0" * channels * int(sample_rate * seconds))


def test_speech_chunks_preserve_controlled_sentence_and_paragraph_pauses() -> None:
    text = (
        "This is the first sentence. This is the second sentence.\n\n"
        "This starts a new paragraph."
    )

    assert PocketTTSService._speech_chunks(text, max_words=5) == [
        ("This is the first sentence.", 0.10),
        ("This is the second sentence.", 0.25),
        ("This starts a new paragraph.", 0.0),
    ]


def test_speech_chunks_split_long_input() -> None:
    assert PocketTTSService._speech_chunks(
        "one two three four five six seven", max_words=3
    ) == [
        ("one two three", 0.10),
        ("four five six", 0.10),
        ("seven", 0.0),
    ]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_combine_samples_normalizes_mixed_audio(tmp_path: Path) -> None:
    mono = tmp_path / "mono.wav"
    stereo = tmp_path / "stereo.wav"
    output = tmp_path / "conditioning.wav"
    _silent_wav(mono, sample_rate=16_000, channels=1, seconds=0.1)
    _silent_wav(stereo, sample_rate=48_000, channels=2, seconds=0.1)

    PocketTTSService._combine_samples([mono, stereo], output)

    with wave.open(str(output), "rb") as combined:
        assert combined.getnchannels() == 1
        assert combined.getframerate() == 24_000
        assert combined.getnframes() == 4_800


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_combine_sequence_inserts_silence(tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "sequence.wav"
    _silent_wav(first, sample_rate=24_000, channels=1, seconds=0.1)
    _silent_wav(second, sample_rate=24_000, channels=1, seconds=0.1)

    PocketTTSService._combine_sequence_sync(
        [(first, 1.0), (None, 0.2), (second, 2.0)], output
    )

    with wave.open(str(output), "rb") as combined:
        assert combined.getnchannels() == 1
        assert combined.getframerate() == 24_000
        assert combined.getnframes() == 9_600


@pytest.mark.parametrize(
    ("url", "start", "duration"),
    [
        ("https://example.com/video", 0, 10),
        ("https://youtube.com.evil.test/watch?v=abc", 0, 10),
        ("https://youtu.be/abc", -1, 10),
        ("https://youtu.be/abc", 0, 31),
    ],
)
def test_youtube_request_validation_rejects_unsafe_inputs(
    url: str, start: int, duration: int
) -> None:
    with pytest.raises(ValueError):
        PocketTTSService._validate_youtube_request(url, start, duration)


def test_youtube_download_uses_requested_time_range(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url: str, download: bool):
            output = Path(captured["outtmpl"].replace("%(ext)s", "webm"))
            output.write_bytes(b"audio")
            return {"id": "abc123", "duration": 100}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)

    filename, content = PocketTTSService._download_youtube_sample_sync(
        "https://youtu.be/abc123", start=12, duration=8, max_bytes=1024
    )

    requested_ranges = list(
        captured["download_ranges"]({"duration": 100}, None)
    )
    assert requested_ranges == [{"start_time": 12, "end_time": 20}]
    assert filename == "youtube-abc123.webm"
    assert content == b"audio"
