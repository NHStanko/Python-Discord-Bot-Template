from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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

    async def delete(self, name: str) -> None:
        slug = self.store.normalize_name(name)
        async with self._lock:
            self.store.delete_voice(slug)
            self._states.pop(slug, None)
