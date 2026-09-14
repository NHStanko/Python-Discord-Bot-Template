from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from helpers.voice_store import VoiceStore


class PocketTTSService:
    """Serialize Pocket TTS access because its model state is not thread-safe."""

    def __init__(self, store: VoiceStore, language: str = "english"):
        self.store = store
        self.language = language
        self._model: Any = None
        self._states: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def _get_model(self) -> Any:
        if self._model is None:
            from pocket_tts import TTSModel

            self._model = TTSModel.load_model(language=self.language)
            self._model.to("cpu")
        return self._model

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
        seconds_per_sample = 30 / len(samples)
        filters = [
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=24000:"
            f"channel_layouts=mono,atrim=duration={seconds_per_sample},"
            f"asetpts=PTS-STARTPTS[a{index}]"
            for index in range(len(samples))
        ]
        inputs = "".join(f"[a{index}]" for index in range(len(samples)))
        filter_graph = ";".join(
            filters + [f"{inputs}concat=n={len(samples)}:v=0:a=1[out]"]
        )
        command.extend(
            ["-filter_complex", filter_graph, "-map", "[out]", "-t", "30", str(destination)]
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
        from pocket_tts import export_model_state

        model = self._get_model()
        voice_dir = self.store.voices_dir / slug
        combined = voice_dir / "conditioning.wav"
        pending = voice_dir / "voice.pending"
        self._combine_samples(self.store.sample_paths(slug), combined)
        state = model.get_state_for_audio_prompt(combined, truncate=True)
        export_model_state(state, pending)
        pending.replace(voice_dir / "voice.safetensors")
        self.store.mark_trained(slug)
        self._states[slug] = state

    async def train(self, name: str) -> None:
        slug = self.store.normalize_name(name)
        async with self._lock:
            await asyncio.to_thread(self._train_sync, slug)

    def _synthesize_sync(self, slug: str, text: str, output: Path) -> None:
        import scipy.io.wavfile

        model = self._get_model()
        state = self._states.get(slug)
        if state is None:
            state = model.get_state_for_audio_prompt(self.store.state_path(slug))
            self._states[slug] = state
        audio = model.generate_audio(state, text)
        scipy.io.wavfile.write(output, model.sample_rate, audio.detach().cpu().numpy())

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
            filters + [f"{inputs}concat=n={len(parts)}:v=0:a=1[out]"]
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
