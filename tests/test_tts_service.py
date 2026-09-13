import shutil
import wave
from pathlib import Path

import pytest

from helpers.tts_service import PocketTTSService


def _silent_wav(path: Path, sample_rate: int, channels: int, seconds: float) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\0\0" * channels * int(sample_rate * seconds))


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
