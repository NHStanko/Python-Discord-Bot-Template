import pytest

from helpers.tts_sequence import (
    RandomSpeechSegment,
    SilenceSegment,
    SpeechSegment,
    parse_tts_sequence,
)


def test_sequence_parses_voices_and_pauses() -> None:
    assert parse_tts_sequence(
        "(forsen) hey i'm forsen (pause) 2.5s (xqc) hi forsen"
    ) == [
        SpeechSegment("forsen", "hey i'm forsen"),
        SilenceSegment(2.5),
        SpeechSegment("xqc", "hi forsen"),
    ]


def test_sequence_parses_random_voice() -> None:
    assert parse_tts_sequence("(random) surprise me") == [
        RandomSpeechSegment("surprise me")
    ]


def test_silence_remains_a_pause_alias() -> None:
    assert parse_tts_sequence("(silence) 1") == [SilenceSegment(1)]


@pytest.mark.parametrize(
    "script",
    [
        "hello (forsen) world",
        "(forsen)",
        "(pause) nope",
        "(pause) 31",
    ],
)
def test_sequence_rejects_invalid_scripts(script: str) -> None:
    with pytest.raises(ValueError):
        parse_tts_sequence(script)


def test_sequence_does_not_apply_an_application_text_limit() -> None:
    long_text = "word " * 2_000

    assert parse_tts_sequence(f"(one) {long_text}") == [
        SpeechSegment("one", long_text.strip())
    ]
