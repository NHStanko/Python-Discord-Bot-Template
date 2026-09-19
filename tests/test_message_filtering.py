from helpers.message_handler import is_dollar_amount_message


def test_dollar_amount_messages_are_ignored() -> None:
    assert is_dollar_amount_message("$5")
    assert is_dollar_amount_message("$20.00")
    assert is_dollar_amount_message("$5 million")
    assert is_dollar_amount_message("$ 50")


def test_text_commands_are_not_treated_as_dollar_amounts() -> None:
    assert not is_dollar_amount_message("$brock Balatro")
    assert not is_dollar_amount_message("$play 5")
    assert not is_dollar_amount_message("I paid $5")
    assert not is_dollar_amount_message("$")
