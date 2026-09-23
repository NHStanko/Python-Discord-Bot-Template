import asyncio
import shutil
import subprocess
import sys
import wave
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.io.wavfile
import yt_dlp

from helpers.tts_service import ChatterboxTTSService
from helpers.voice_store import VOICE_STATE_FILENAME, VoiceStore


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

    assert ChatterboxTTSService._speech_chunks(text, max_words=5) == [
        ("This is the first sentence.", 0.10),
        ("This is the second sentence.", 0.25),
        ("This starts a new paragraph.", 0.0),
    ]


def test_speech_chunks_split_long_input() -> None:
    assert ChatterboxTTSService._speech_chunks(
        "one two three four five six seven", max_words=3
    ) == [
        ("one two three", 0.10),
        ("four five six", 0.10),
        ("seven", 0.0),
    ]


def test_speech_chunks_keep_sentence_and_prefer_clause_boundaries() -> None:
    sentence = " ".join(["word"] * 45) + "."
    assert ChatterboxTTSService._speech_chunks(sentence) == [(sentence, 0.0)]
    assert ChatterboxTTSService._speech_chunks(
        "one two three, four five six seven eight", max_words=5
    ) == [("one two three,", 0.1), ("four five six seven eight", 0.0)]


class FakeAudio:
    def __init__(self, samples):
        self.samples = np.asarray(samples, dtype=np.float32)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.samples


@pytest.fixture
def nano_runtime(monkeypatch):
    class State:
        def __init__(self, name):
            self.name = name

        def save(self, path):
            Path(path).write_text(self.name)

        @classmethod
        def load(cls, path, map_location):
            assert map_location == "cpu"
            return cls(Path(path).read_text())

        def to(self, device):
            assert device == "cpu"
            return self

    class Model:
        sr = 24000

        def __init__(self):
            self.conds = None
            self.calls = []

        def prepare_conditionals(self, path):
            self.conds = State(Path(path).parent.name)

        def generate(self, text):
            self.calls.append((self.conds.name, text))
            return FakeAudio(np.full((1, 2400), 0.2, dtype=np.float32))

    model = Model()

    def load_model(*, device, nano):
        assert device == "cpu" and nano is True
        return model

    monkeypatch.setitem(sys.modules, "chatterbox", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "chatterbox.tts_turbo", SimpleNamespace(
        ChatterboxTurboTTS=SimpleNamespace(from_pretrained=load_model),
        Conditionals=State,
    ))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        inference_mode=nullcontext, set_num_threads=lambda threads: None,
    ))

    # Exercise the model logic in this process with the fake runtime. Separate
    # worker tests cover the real subprocess transport and cancellation.
    async def inline_job(self, operation, *args):
        if operation == "synthesize":
            slug, text, output = args
            self._synthesize_sync(slug, text, Path(output))
        else:
            getattr(self, f"_{operation}_sync")(*args)

    monkeypatch.setattr(ChatterboxTTSService, "_run_model_job", inline_job)
    return model


def test_saved_voices_reload_and_switch_without_speaker_leakage(tmp_path, nano_runtime):
    store = VoiceStore(tmp_path)
    for name in ("first", "second"):
        store.create_voice(name, 1)
        (store.voices_dir / name / VOICE_STATE_FILENAME).write_text(name)
        store.mark_trained(name)
    service = ChatterboxTTSService(store)
    for name in ("first", "second", "first"):
        output = asyncio.run(service.synthesize(name, "Hello there."))
        rate, samples = scipy.io.wavfile.read(output)
        assert rate == 24000 and len(samples) == 2400
        output.unlink()
    assert nano_runtime.calls == [
        ("first", "Hello there."), ("second", "Hello there."),
        ("first", "Hello there."),
    ]


def _legacy_voice(store):
    store.create_voice("legacy", 1)
    store.add_sample("legacy", "reference.wav", b"retained sample")
    old_state = store.voices_dir / "legacy" / "voice.safetensors"
    old_state.write_bytes(b"pocket state")
    with store._connect() as db:
        db.execute("UPDATE voices SET state_filename = 'voice.safetensors'")
    return old_state


def test_legacy_voice_rebuilds_once_and_retains_samples(tmp_path, monkeypatch, nano_runtime):
    store = VoiceStore(tmp_path)
    old_state = _legacy_voice(store)
    store.set_volume("legacy", 1.4)
    service = ChatterboxTTSService(store)
    builds = []

    def combine(paths, destination):
        builds.append(paths)
        _silent_wav(destination, 24000, 1, 6)

    monkeypatch.setattr(service, "_combine_samples", combine)
    for _ in range(2):
        asyncio.run(service.synthesize("legacy", "Hello.")).unlink()
    assert len(builds) == 1
    assert store.state_path("legacy").name == VOICE_STATE_FILENAME
    assert old_state.read_bytes() == b"pocket state"
    assert store.sample_paths("legacy")[0].read_bytes() == b"retained sample"
    assert store.get_voice("legacy").volume == 1.4


def test_failed_migration_preserves_legacy_profile_and_cleans_output(
    tmp_path, monkeypatch, nano_runtime
):
    store = VoiceStore(tmp_path)
    old_state = _legacy_voice(store)
    service = ChatterboxTTSService(store)
    monkeypatch.setattr(service, "_combine_samples", lambda paths, dest:
                        _silent_wav(dest, 24000, 1, 5))
    with pytest.raises(ValueError, match="more than 5 seconds"):
        asyncio.run(service.synthesize("legacy", "Hello."))
    assert store.state_path("legacy") == old_state
    assert not list(store.generated_dir.iterdir())
    assert "legacy" not in service._states


def test_audio_keeps_pauses_and_word_endings_and_bounds_peaks():
    samples = np.concatenate([np.zeros(1000), np.full(1000, 2.0), np.zeros(1000)])
    result = ChatterboxTTSService._prepare_audio(FakeAudio(samples), 24000)
    assert len(result) == len(samples)
    assert np.flatnonzero(result).tolist() == list(range(1000, 2000))
    assert np.max(np.abs(result)) == pytest.approx(0.95)


@pytest.mark.parametrize("samples", [[], [np.nan], [np.inf]])
def test_bad_generation_is_rejected(samples):
    with pytest.raises(ValueError, match="invalid audio"):
        ChatterboxTTSService._prepare_audio(FakeAudio(samples), 24000)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_reference_processing_preserves_speech_after_internal_pause(tmp_path):
    rate = 24000
    tone = (0.2 * np.sin(2 * np.pi * 220 * np.arange(rate * 3) / rate)).astype(np.float32)
    samples = np.concatenate([tone, np.zeros(rate), tone]).astype(np.float32)
    source, destination = tmp_path / "source.wav", tmp_path / "reference.wav"
    scipy.io.wavfile.write(source, rate, samples)
    ChatterboxTTSService._combine_samples([source], destination)
    output_rate, output = scipy.io.wavfile.read(destination)
    assert len(output) / output_rate > 6.9
    assert np.max(np.abs(output[5 * output_rate:6 * output_rate])) > 100


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
@pytest.mark.parametrize("sequence", [False, True])
def test_volume_limiter_prevents_clipping_without_truncation(tmp_path, sequence):
    rate = 24000
    tone = (0.8 * np.sin(2 * np.pi * 220 * np.arange(rate) / rate)).astype(np.float32)
    source, output = tmp_path / "source.wav", tmp_path / "output.wav"
    scipy.io.wavfile.write(source, rate, tone)
    if sequence:
        ChatterboxTTSService._combine_sequence_sync([(source, 4.0)], output)
    else:
        options = ChatterboxTTSService.playback_options(4.0).split()
        subprocess.run(["ffmpeg", "-y", "-i", str(source), *options, str(output)],
                       capture_output=True, check=True)
    output_rate, audio = scipy.io.wavfile.read(output)
    assert len(audio) == len(tone) and output_rate == rate
    assert np.max(np.abs(audio.astype(np.float64))) <= 0.951 * 32768
    assert np.max(np.abs(audio[-240:].astype(np.float64))) > 1000


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not installed")
def test_combine_samples_normalizes_mixed_audio(tmp_path: Path) -> None:
    mono = tmp_path / "mono.wav"
    stereo = tmp_path / "stereo.wav"
    output = tmp_path / "conditioning.wav"
    _silent_wav(mono, sample_rate=16_000, channels=1, seconds=0.1)
    _silent_wav(stereo, sample_rate=48_000, channels=2, seconds=0.1)

    ChatterboxTTSService._combine_samples([mono, stereo], output)

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

    ChatterboxTTSService._combine_sequence_sync(
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
        ChatterboxTTSService._validate_youtube_request(url, start, duration)


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

    filename, content = ChatterboxTTSService._download_youtube_sample_sync(
        "https://youtu.be/abc123", start=12, duration=8, max_bytes=1024
    )

    requested_ranges = list(
        captured["download_ranges"]({"duration": 100}, None)
    )
    assert requested_ranges == [{"start_time": 12, "end_time": 20}]
    assert filename == "youtube-abc123.webm"
    assert content == b"audio"
