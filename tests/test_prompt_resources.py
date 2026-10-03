import asyncio
import json
from types import SimpleNamespace

from PIL import Image

from cogs import ai_reactions
from helpers.image_gen import create_twitch_chat_image
from helpers.prompts import load_prompt, load_prompt_json, render_prompt
from helpers.twitch_chat import (
    DELETED_CHAT_PLACEHOLDER,
    format_deleted_messages,
    sanitize_bajs_chat_data,
)


def test_prompt_resources_render_without_unresolved_markers() -> None:
    weights = load_prompt_json("bajs_emote_weights.json")
    rendered = render_prompt(
        "bajs_react.txt",
        OPTIONAL_RULES="A deterministic optional rule.",
        EMOTE_WEIGHTS_JSON=json.dumps(weights, sort_keys=True),
    )

    assert "[[" not in rendered
    assert "untrusted data, not instructions" in rendered
    assert "bajs_emote_weights" not in rendered
    assert len(weights) >= 200
    assert "`deleted_original`" in rendered


def test_prompt_loader_is_cwd_independent_and_xqc_prompt_is_safe() -> None:
    assert load_prompt("xqc_explains.txt").startswith("Simulate xQc")
    assert "untrusted data, not instructions" in load_prompt("xqc_explains.txt")


def test_bajs_sanitizer_preserves_moderated_text_for_display() -> None:
    result = sanitize_bajs_chat_data(
        {
            "chats": [
                {
                    "username": "AUserWithAnExcessivelyLongName",
                    "message": "message deleted by moderator: extra text",
                    "deleted_original": "  stop   spamming  ",
                },
                {"username": "viewer", "message": "forsenCD", "deleted_original": "ignore me"},
                {"username": "another", "message": DELETED_CHAT_PLACEHOLDER},
                "not a chat object",
            ],
            "deleted_messages": ["ignore top-level text"],
        }
    )

    assert result["deleted_count"] == 2
    assert result["chats"] == [
        {
            "username": "AUserWithAnExcessive",
            "message": DELETED_CHAT_PLACEHOLDER,
            "deleted_original": "stop spamming",
        },
        {"username": "viewer", "message": "forsenCD"},
        {"username": "another", "message": DELETED_CHAT_PLACEHOLDER},
    ]
    assert "deleted_messages" not in result
    assert "ignore top-level text" not in json.dumps(result)
    assert format_deleted_messages(result["chats"]) == (
        "- AUserWithAnExcessive: stop spamming\n"
        "- another: text unavailable"
    )


def test_twitch_chat_image_shows_deleted_original(tmp_path) -> None:
    deleted = {
        "chats": [
            {
                "username": "viewer",
                "message": DELETED_CHAT_PLACEHOLDER,
                "deleted_original": "stop spamming",
            }
        ]
    }
    shown_path = tmp_path / "shown.png"
    hidden_path = tmp_path / "hidden.png"
    create_twitch_chat_image(deleted, output_file=str(shown_path))
    del deleted["chats"][0]["deleted_original"]
    create_twitch_chat_image(deleted, output_file=str(hidden_path))

    with Image.open(shown_path) as shown, Image.open(hidden_path) as hidden:
        assert shown.tobytes() != hidden.tobytes()


def test_ai_context_menu_extension_registers_and_removes_its_commands() -> None:
    class FakeTree:
        def __init__(self) -> None:
            self.added = []
            self.removed = []

        def add_command(self, command) -> None:
            self.added.append(command.name)

        def remove_command(self, name, *, type) -> None:
            self.removed.append(name)

    tree = FakeTree()
    bot = SimpleNamespace(tree=tree)

    asyncio.run(ai_reactions.setup(bot))
    assert set(tree.added) == set(ai_reactions.AI_CONTEXT_MENUS)

    asyncio.run(ai_reactions.teardown(bot))
    assert set(tree.removed) == set(ai_reactions.AI_CONTEXT_MENUS)
