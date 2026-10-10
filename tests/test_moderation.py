import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.moderation import Moderation


def make_context(deleted_count=0):
    progress = SimpleNamespace(id=100, delete=AsyncMock())
    channel = SimpleNamespace(
        purge=AsyncMock(return_value=[object() for _ in range(deleted_count)]),
        send=AsyncMock(),
    )
    context = SimpleNamespace(
        author="Moderator", channel=channel, send=AsyncMock(return_value=progress)
    )
    return context, progress


@pytest.mark.parametrize("amount", [0, -1, -100])
def test_purge_rejects_nonpositive_amount(amount):
    context, progress = make_context()

    asyncio.run(Moderation.purge.callback(Moderation(None), context, amount))

    context.send.assert_awaited_once_with(
        "The amount must be at least 1.", ephemeral=True
    )
    context.channel.purge.assert_not_awaited()
    progress.delete.assert_not_awaited()


@pytest.mark.parametrize("deleted_count", [0, 2, 5])
def test_purge_uses_status_message_as_boundary_and_reports_actual_count(deleted_count):
    context, progress = make_context(deleted_count)

    asyncio.run(Moderation.purge.callback(Moderation(None), context, 5))

    context.channel.purge.assert_awaited_once_with(limit=5, before=progress)
    progress.delete.assert_awaited_once_with()
    embed = context.channel.send.call_args.kwargs["embed"]
    assert embed.description == f"**Moderator** cleared **{deleted_count}** messages!"


def test_purge_reports_count_when_status_message_was_already_deleted():
    context, progress = make_context(2)
    progress.delete.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "Unknown Message"
    )

    asyncio.run(Moderation.purge.callback(Moderation(None), context, 5))

    embed = context.channel.send.call_args.kwargs["embed"]
    assert embed.description == "**Moderator** cleared **2** messages!"
