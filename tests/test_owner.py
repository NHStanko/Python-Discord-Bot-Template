import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cogs.owner import Owner


def make_context(guild=None):
    tree = SimpleNamespace(
        clear_commands=Mock(), copy_global_to=Mock(), sync=AsyncMock()
    )
    return SimpleNamespace(
        guild=guild, bot=SimpleNamespace(tree=tree), send=AsyncMock()
    )


@pytest.mark.parametrize("command", [Owner.sync, Owner.unsync])
def test_guild_scope_in_dm_does_not_modify_or_sync_commands(command):
    context = make_context()

    asyncio.run(command.callback(Owner(context.bot), context, "guild"))

    context.bot.tree.clear_commands.assert_not_called()
    context.bot.tree.copy_global_to.assert_not_called()
    context.bot.tree.sync.assert_not_awaited()
    context.send.assert_awaited_once()
    embed = context.send.call_args.kwargs["embed"]
    assert embed.description == "The `guild` scope can only be used in a server."
    assert embed.color.value == 0xE02B2B


@pytest.mark.parametrize("command", [Owner.sync, Owner.unsync])
@pytest.mark.parametrize("guild", [None, SimpleNamespace(id=123)])
def test_global_scope_can_be_used_in_dm_or_server(command, guild):
    context = make_context(guild)

    asyncio.run(command.callback(Owner(context.bot), context, "global"))

    context.bot.tree.sync.assert_awaited_once_with()
    context.bot.tree.copy_global_to.assert_not_called()
    if command is Owner.unsync:
        context.bot.tree.clear_commands.assert_called_once_with(guild=None)
    else:
        context.bot.tree.clear_commands.assert_not_called()
    context.send.assert_awaited_once()
    assert "globally" in context.send.call_args.kwargs["embed"].description


@pytest.mark.parametrize("command", [Owner.sync, Owner.unsync])
def test_guild_scope_in_server_uses_current_guild(command):
    guild = SimpleNamespace(id=123)
    context = make_context(guild)

    asyncio.run(command.callback(Owner(context.bot), context, "guild"))

    context.bot.tree.sync.assert_awaited_once_with(guild=guild)
    if command is Owner.unsync:
        context.bot.tree.clear_commands.assert_called_once_with(guild=guild)
        context.bot.tree.copy_global_to.assert_not_called()
    else:
        context.bot.tree.copy_global_to.assert_called_once_with(guild=guild)
        context.bot.tree.clear_commands.assert_not_called()
    context.send.assert_awaited_once()
