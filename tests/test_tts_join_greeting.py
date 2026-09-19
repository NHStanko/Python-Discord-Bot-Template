from types import SimpleNamespace
from unittest.mock import patch

import discord

from cogs.tts import (
    BROCK_TTS_PROMPT,
    BROCK_USER_ID,
    game_names,
    newly_started_game,
    should_trigger_brock_tts,
    valid_brock_monologue,
)


def activity(name: str, activity_type: discord.ActivityType = discord.ActivityType.playing):
    return SimpleNamespace(name=name, type=activity_type)


def test_game_tts_only_targets_brock() -> None:
    with patch("cogs.tts.secrets.randbelow", return_value=0):
        assert should_trigger_brock_tts(BROCK_USER_ID)
        assert not should_trigger_brock_tts(BROCK_USER_ID + 1)


def test_game_tts_has_one_in_one_hundred_chance() -> None:
    with patch("cogs.tts.secrets.randbelow", return_value=0):
        assert should_trigger_brock_tts(BROCK_USER_ID)
    with patch("cogs.tts.secrets.randbelow", return_value=1):
        assert not should_trigger_brock_tts(BROCK_USER_ID)


def test_game_detection_ignores_non_game_activities() -> None:
    activities = (
        activity("Custom Status", discord.ActivityType.custom),
        activity("Balatro"),
    )

    assert game_names(activities) == ("Balatro",)
    assert newly_started_game((), activities) == "Balatro"
    assert newly_started_game((activity("Balatro"),), activities) is None


def test_monologue_requires_two_paragraphs_and_target_word_count() -> None:
    first = " ".join(["word"] * 125)
    second = " ".join(["word"] * 125)

    assert valid_brock_monologue(f"{first}\n\n{second}")
    assert not valid_brock_monologue(f"{first} {second}")
    assert not valid_brock_monologue("short\n\nresponse")


def test_brock_prompt_template_contains_dynamic_game_input() -> None:
    template = BROCK_TTS_PROMPT.read_text(encoding="utf-8")
    rendered = template.replace("[INSERT GAME HERE]", "Balatro").replace(
        "[OPTIONAL]", "Not provided"
    )

    assert "CURRENT GAME: Balatro" in rendered
    assert "[INSERT GAME HERE]" not in rendered
    assert "You have web search available." in rendered
