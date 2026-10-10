import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs import ai_reactions


@pytest.mark.parametrize("failure", ["context", "prompt", "reply", None])
def test_bajs_reaction_cleans_images_on_success_and_failure(
    tmp_path, monkeypatch, failure
):
    downloaded = tmp_path / "download.png"
    downloaded.write_bytes(b"downloaded image")
    generated = tmp_path / "result.png"
    helper = SimpleNamespace(
        generate_content=AsyncMock(
            return_value=(
                json.dumps({"chats": [{"username": "viewer", "message": "hello"}]}),
                None,
            )
        )
    )
    interaction = SimpleNamespace(
        client=SimpleNamespace(logger=logging.getLogger("test")),
        user=SimpleNamespace(name="viewer"),
        response=SimpleNamespace(defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    sent_files = []

    async def reply(*, file):
        assert not file.fp.closed
        assert generated.exists()
        sent_files.append(file)
        if failure == "reply":
            raise RuntimeError("Discord delivery failed")

    message = SimpleNamespace(id=123, reply=AsyncMock(side_effect=reply))
    monkeypatch.setattr(
        ai_reactions, "load_ai_helper_from_config", lambda *a, **k: helper
    )
    monkeypatch.setattr(
        ai_reactions,
        "extract_message_content",
        AsyncMock(
            return_value=("hello", str(downloaded), None, None, None, [str(downloaded)])
        ),
    )
    context = AsyncMock(return_value=("hello", str(downloaded)))
    if failure == "context":
        context.side_effect = RuntimeError("Context failed")
    monkeypatch.setattr(ai_reactions, "add_message_context", context)

    def load_weights(*args):
        if failure == "prompt":
            raise ValueError("Invalid prompt resource")
        return {}

    monkeypatch.setattr(ai_reactions, "load_prompt_json", load_weights)
    monkeypatch.setattr(ai_reactions, "render_prompt", lambda *a, **k: "system prompt")
    monkeypatch.setattr(ai_reactions, "load_emote_map", lambda: {})
    monkeypatch.setattr(ai_reactions, "load_loyalty_badges", lambda: {})

    def render(*args, **kwargs):
        generated.write_bytes(b"generated image")
        return str(generated)

    monkeypatch.setattr(ai_reactions, "create_twitch_chat_image", render)
    asyncio.run(ai_reactions.test_ai(interaction, message))

    assert not downloaded.exists()
    assert not generated.exists()
    assert all(file.fp.closed for file in sent_files)
    if failure in {"context", "prompt"}:
        helper.generate_content.assert_not_awaited()
        message.reply.assert_not_awaited()
    else:
        message.reply.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
