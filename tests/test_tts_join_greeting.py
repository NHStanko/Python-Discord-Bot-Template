from unittest.mock import patch

from cogs.tts import BROCK_USER_ID, should_play_join_greeting


def test_join_greeting_only_targets_brock() -> None:
    with patch("cogs.tts.secrets.randbelow", return_value=0):
        assert should_play_join_greeting(BROCK_USER_ID)
        assert not should_play_join_greeting(BROCK_USER_ID + 1)


def test_join_greeting_has_one_in_one_hundred_chance() -> None:
    with patch("cogs.tts.secrets.randbelow", return_value=0):
        assert should_play_join_greeting(BROCK_USER_ID)
    with patch("cogs.tts.secrets.randbelow", return_value=1):
        assert not should_play_join_greeting(BROCK_USER_ID)
