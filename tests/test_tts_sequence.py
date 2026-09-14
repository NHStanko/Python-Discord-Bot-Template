import pytest

from helpers.tts_sequence import SilenceSegment, SpeechSegment, parse_tts_sequence


def test_sequence_parses_voices_and_silence() -> None:
    assert parse_tts_sequence(
        "(forsen) hey i'm forsen (silence) 2.5s (xqc) hi forsen"
    ) == [
        SpeechSegment("forsen", "hey i'm forsen"),
        SilenceSegment(2.5),
        SpeechSegment("xqc", "hi forsen"),
    ]


@pytest.mark.parametrize(
    "script",
    [
        "hello (forsen) world",
        "(forsen)",
        "(silence) nope",
        "(silence) 31",
    ],
)
def test_sequence_rejects_invalid_scripts(script: str) -> None:
    with pytest.raises(ValueError):
        parse_tts_sequence(script)


def test_sequence_enforces_total_spoken_text_limit() -> None:
    with pytest.raises(ValueError):
        parse_tts_sequence("(one) 12345 (two) 67890", max_text_length=9)
