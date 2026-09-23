from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from helpers.voice_store import VOICE_STATE_FILENAME, VoiceStore

TTS_CHUNK_WORDS = 60
TTS_SENTENCE_PAUSE = 0.10
TTS_PARAGRAPH_PAUSE = 0.25
# Flush and compensate the 5 ms lookahead, including on FFmpeg 4 (which has no
# alimiter latency option). Disable makeup gain to preserve saved volume levels.
TTS_LIMITER = (
    "apad=pad_dur=0.005,alimiter=limit=0.95:level=false:attack=5,"
    "atrim=start=0.005,asetpts=PTS-STARTPTS"
)
_SENTENCE_BOUNDARY = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"']))\s+")


class ChatterboxTTSService:
    """Serialize CPU Nano inference and switching its active voice conditionals."""

    def __init__(self, store: VoiceStore, cpu_threads: int = 8):
        if cpu_threads < 1:
            raise ValueError("TTS CPU threads must be at least 1")
        self.store = store
        self.cpu_threads = cpu_threads
        self._model: Any = None
        self._states: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def _get_model(self) -> Any:
        if self._model is None:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            torch.set_num_threads(self.cpu_threads)
            self._model = ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)
        return self._model

    @staticmethod
    def playback_options(volume: float) -> str:
        return f"-af volume={volume:.2f},{TTS_LIMITER}"

    @staticmethod
    def _validate_youtube_request(url: str, start: int, duration: int) -> str:
        parsed = urlparse(url.strip())
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or hostname not in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }:
            raise ValueError("Use a valid YouTube or youtu.be URL")
        if start < 0:
            raise ValueError("Start time cannot be negative")
        if duration < 1 or duration > 30:
            raise ValueError("Duration must be between 1 and 30 seconds")
        return parsed.geturl()

    @classmethod
    def _download_youtube_sample_sync(
        cls, url: str, start: int, duration: int, max_bytes: int
    ) -> tuple[str, bytes]:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import download_range_func

        validated_url = cls._validate_youtube_request(url, start, duration)
        with tempfile.TemporaryDirectory(prefix="tts-youtube-") as temp_dir:
            output_template = str(Path(temp_dir) / "sample.%(ext)s")
            options = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "max_filesize": max(max_bytes * 5, 50 * 1024 * 1024),
                "download_ranges": download_range_func(
                    None, [(start, start + duration)]
                ),
                "force_keyframes_at_cuts": True,
                "socket_timeout": 30,
                "retries": 3,
            }
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(validated_url, download=True)

            candidates = [
                path
                for path in Path(temp_dir).iterdir()
                if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
            ]
            if len(candidates) != 1:
                raise ValueError("YouTube did not produce a usable audio clip")
            clip = candidates[0]
            content = clip.read_bytes()
            if not content:
                raise ValueError("YouTube produced an empty audio clip")
            if len(content) > max_bytes:
                limit = max_bytes // 1024 // 1024
                raise ValueError(f"Downloaded clip is larger than {limit} MB")
            video_id = str(info.get("id") or "clip")
            return f"youtube-{video_id}{clip.suffix.lower()}", content

    async def download_youtube_sample(
        self, url: str, start: int, duration: int, max_bytes: int
    ) -> tuple[str, bytes]:
        return await asyncio.to_thread(
            self._download_youtube_sample_sync, url, start, duration, max_bytes
        )

    @staticmethod
    def _combine_samples(samples: list[Path], destination: Path) -> None:
        if not samples:
            raise ValueError("At least one training sample is required")
        command = ["ffmpeg", "-y"]
        for sample in samples:
            command.extend(["-i", str(sample)])
        seconds_per_sample = 15 / len(samples)
        filters = [
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=24000:"
            "channel_layouts=mono,"
            "silenceremove=start_periods=1:start_duration=0.05:"
            "start_threshold=-50dB,"
            "loudnorm=I=-20:TP=-2:LRA=11,"
            "aformat=sample_fmts=fltp:sample_rates=24000:channel_layouts=mono,"
            f"apad=pad_dur=0.1,atrim=duration={seconds_per_sample},"
            f"asetpts=PTS-STARTPTS[a{index}]"
            for index in range(len(samples))
        ]
        inputs = "".join(f"[a{index}]" for index in range(len(samples)))
        filter_graph = ";".join(
            filters + [f"{inputs}concat=n={len(samples)}:v=0:a=1[out]"]
        )
        command.extend(
            ["-filter_complex", filter_graph, "-map", "[out]", "-t", "15", str(destination)]
        )
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode:
            detail = (
                result.stderr.strip().splitlines()[-1]
                if result.stderr.strip()
                else "unknown error"
            )
            raise ValueError(f"FFmpeg could not process the attachment: {detail}")

    def _train_sync(self, slug: str) -> None:
        import torch

        voice_dir = self.store.voices_dir / slug
        combined = voice_dir / "chatterbox-reference.wav"
        pending = voice_dir / "chatterbox-nano-v1.pending"
        self._combine_samples(self.store.sample_paths(slug), combined)
        with wave.open(str(combined), "rb") as reference:
            duration = reference.getnframes() / reference.getframerate()
        if duration <= 5:
            raise ValueError(
                "Chatterbox needs more than 5 seconds of reference audio. "
                "Add a clean 6-15 second speech recording, then retrain."
            )
        model = self._get_model()
        with torch.inference_mode():
            model.prepare_conditionals(str(combined))
        state = model.conds
        try:
            state.save(pending)
            pending.replace(voice_dir / VOICE_STATE_FILENAME)
        finally:
            pending.unlink(missing_ok=True)
        self.store.mark_trained(slug)
        self._states[slug] = state

    async def train(self, name: str) -> None:
        slug = self.store.normalize_name(name)
        async with self._lock:
            await asyncio.to_thread(self._train_sync, slug)

    @staticmethod
    def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
        words = sentence.split()
        chunks = []
        while len(words) > max_words:
            # Prefer a clause boundary over restarting speech mid-phrase.
            boundary = next(
                (index for index in range(max_words, max_words // 2, -1)
                 if words[index - 1].endswith((",", ";", ":"))),
                max_words,
            )
            chunks.append(" ".join(words[:boundary]))
            words = words[boundary:]
        if words:
            chunks.append(" ".join(words))
        return chunks

    @classmethod
    def _speech_chunks(
        cls, text: str, max_words: int = TTS_CHUNK_WORDS
    ) -> list[tuple[str, float]]:
        """Create short generation units with an explicit pause after each one."""
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[tuple[str, float]] = []
        for paragraph_index, paragraph in enumerate(paragraphs):
            normalized = " ".join(paragraph.split())
            sentences = [
                piece.strip()
                for piece in _SENTENCE_BOUNDARY.split(normalized)
                if piece.strip()
            ]
            units = [
                unit
                for sentence in sentences
                for unit in cls._split_long_sentence(sentence, max_words)
            ]
            grouped: list[str] = []
            grouped_words = 0
            for unit in units:
                unit_words = len(unit.split())
                if grouped and grouped_words + unit_words > max_words:
                    chunks.append((" ".join(grouped), TTS_SENTENCE_PAUSE))
                    grouped = []
                    grouped_words = 0
                grouped.append(unit)
                grouped_words += unit_words
            if grouped:
                pause = (
                    TTS_PARAGRAPH_PAUSE
                    if paragraph_index < len(paragraphs) - 1
                    else 0.0
                )
                chunks.append((" ".join(grouped), pause))
        return chunks

    @staticmethod
    def _prepare_audio(audio: Any, sample_rate: int) -> Any:
        """Keep natural pauses and soften only the outer 5 ms to prevent clicks."""
        import numpy as np

        samples = audio.detach().cpu().numpy().reshape(-1).copy()
        if not samples.size or not np.isfinite(samples).all():
            raise ValueError("Chatterbox generated empty or invalid audio; try again")
        fade = min(int(sample_rate * 0.005), samples.size // 2)
        if fade:
            ramp = np.linspace(0, 1, fade, dtype=samples.dtype)
            samples[:fade] *= ramp
            samples[-fade:] *= ramp[::-1]
        peak = float(np.max(np.abs(samples)))
        if peak > 0.95:
            samples *= 0.95 / peak
        return samples

    def _synthesize_sync(self, slug: str, text: str, output: Path) -> None:
        import numpy as np
        import scipy.io.wavfile
        import torch
        from chatterbox.tts_turbo import Conditionals

        chunks = self._speech_chunks(text)
        if not chunks:
            raise ValueError("Text cannot be empty")
        state = self._states.get(slug)
        if state is None:
            state_path = self.store.state_path(slug)
            if state_path.name == "voice.safetensors":
                # Pocket embeddings cannot be reused; rebuild from retained samples.
                self._train_sync(slug)
                state = self._states[slug]
            else:
                state = Conditionals.load(state_path, map_location="cpu").to("cpu")
            self._states[slug] = state
        model = self._get_model()
        model.conds = state

        rendered = []
        for chunk, pause_after in chunks:
            with torch.inference_mode():
                audio = model.generate(chunk)
            rendered.append(self._prepare_audio(audio, model.sr))
            if pause_after:
                rendered.append(
                    np.zeros(
                        int(model.sr * pause_after),
                        dtype=rendered[-1].dtype,
                    )
                )
        scipy.io.wavfile.write(output, model.sr, np.concatenate(rendered))

    async def synthesize(self, name: str, text: str) -> Path:
        slug = self.store.normalize_name(name)
        handle = tempfile.NamedTemporaryFile(
            suffix=".wav", dir=self.store.generated_dir, delete=False
        )
        output = Path(handle.name)
        handle.close()
        try:
            async with self._lock:
                await asyncio.to_thread(self._synthesize_sync, slug, text, output)
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    @staticmethod
    def _combine_sequence_sync(
        parts: list[tuple[Path | None, float]], destination: Path
    ) -> None:
        if not parts:
            raise ValueError("A sequence needs at least one segment")

        command = ["ffmpeg", "-y"]
        filters = []
        for index, (audio_path, value) in enumerate(parts):
            if audio_path is None:
                command.extend(
                    [
                        "-f",
                        "lavfi",
                        "-t",
                        str(value),
                        "-i",
                        "anullsrc=channel_layout=mono:sample_rate=24000",
                    ]
                )
                effect = f",atrim=duration={value}"
            else:
                command.extend(["-i", str(audio_path)])
                effect = f",volume={value}"
            filters.append(
                f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=24000:"
                f"channel_layouts=mono{effect},asetpts=PTS-STARTPTS[a{index}]"
            )

        inputs = "".join(f"[a{index}]" for index in range(len(parts)))
        filter_graph = ";".join(
            filters + [f"{inputs}concat=n={len(parts)}:v=0:a=1,{TTS_LIMITER}[out]"]
        )
        command.extend(
            ["-filter_complex", filter_graph, "-map", "[out]", str(destination)]
        )
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode:
            detail = (
                result.stderr.strip().splitlines()[-1]
                if result.stderr.strip()
                else "unknown error"
            )
            raise ValueError(f"FFmpeg could not combine the sequence: {detail}")

    async def combine_sequence(
        self, parts: list[tuple[Path | None, float]]
    ) -> Path:
        handle = tempfile.NamedTemporaryFile(
            suffix=".wav", dir=self.store.generated_dir, delete=False
        )
        output = Path(handle.name)
        handle.close()
        try:
            await asyncio.to_thread(self._combine_sequence_sync, parts, output)
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    async def delete(self, name: str) -> None:
        slug = self.store.normalize_name(name)
        async with self._lock:
            self.store.delete_voice(slug)
            self._states.pop(slug, None)
