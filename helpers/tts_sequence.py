from __future__ import annotations

import re
from dataclasses import dataclass

TAG_PATTERN = re.compile(r"\(([^()\n]{1,32})\)")


@dataclass(frozen=True)
class SpeechSegment:
    voice: str
    text: str


@dataclass(frozen=True)
class RandomSpeechSegment:
    text: str


@dataclass(frozen=True)
class SilenceSegment:
    duration: float


SequenceSegment = SpeechSegment | RandomSpeechSegment | SilenceSegment


def parse_tts_sequence(
    script: str,
    *,
    max_segments: int = 20,
    max_silence: float = 30,
) -> list[SequenceSegment]:
    matches = list(TAG_PATTERN.finditer(script))
    if not matches or script[: matches[0].start()].strip():
        raise ValueError("Start the script with a voice tag such as `(forsen)`")
    if len(matches) > max_segments:
        raise ValueError(f"A sequence may contain at most {max_segments} segments")

    segments: list[SequenceSegment] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        name = match.group(1).strip()
        content = script[match.end() : end].strip()
        normalized_name = name.casefold()
        if normalized_name in {"pause", "silence"}:
            value = content.removesuffix("s").strip()
            try:
                duration = float(value)
            except ValueError as exc:
                raise ValueError("Pause must be a number of seconds") from exc
            if duration <= 0 or duration > max_silence:
                raise ValueError(
                    f"Each pause must be more than 0 and at most {max_silence} seconds"
                )
            segments.append(SilenceSegment(duration))
            continue

        if not content:
            raise ValueError(f"Voice `{name}` needs text to speak")
        if normalized_name == "random":
            segments.append(RandomSpeechSegment(content))
        else:
            segments.append(SpeechSegment(name, content))

    return segments
