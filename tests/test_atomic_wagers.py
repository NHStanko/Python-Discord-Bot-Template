import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.gamba import Gamba
from helpers import db_manager

pytest_plugins = ["test_gambling_database"]


def test_concurrent_allin_losses_settle_once(database, monkeypatch):
    async def exercise():
        await db_manager.update_user_money(123, 10)
        monkeypatch.setattr("cogs.gamba.random.choice", lambda odds: -1)
        ctx = SimpleNamespace(
            author=SimpleNamespace(id=123, mention="@bettor"), send=AsyncMock()
        )
        ready = asyncio.Event()
        selected = 0

        async def select_stake(user_id):
            nonlocal selected
            account = await db_manager.get_user_info(user_id)
            selected += 1
            if selected == 8:
                ready.set()
            await ready.wait()
            return account

        monkeypatch.setattr("cogs.gamba.get_user_info", select_stake)
        await asyncio.gather(
            *(Gamba.allin.callback(Gamba(None), ctx) for _ in range(8))
        )
        account = await db_manager.get_user_info(123)
        assert account["money"] == 0
        assert account["plays"] == 1
        assert account["total_loss"] == -10
        assert account["bankrupt_count"] == 1
        messages = [call.args[0] for call in ctx.send.call_args_list]
        assert messages.count("@bettor went all in and lost 10 coins") == 1
        assert messages.count("You don't have enough coins to gamble that much") == 7

    asyncio.run(exercise())


@pytest.mark.parametrize("amount", [0, -1, 11])
def test_rejected_wagers_do_not_update_account(database, amount):
    async def exercise():
        await db_manager.update_user_money(123, 10)
        before = await db_manager.get_user_info(123)
        if amount < 1:
            with pytest.raises(ValueError):
                await db_manager.settle_wager(123, amount, True)
        else:
            assert await db_manager.settle_wager(123, amount, True) is None
        assert await db_manager.get_user_info(123) == before

    asyncio.run(exercise())


def test_successful_wagers_update_stats(database):
    async def exercise():
        await db_manager.update_user_money(123, 10)
        assert await db_manager.settle_wager(123, 4, True) == {"all_in": False}
        assert await db_manager.settle_wager(123, 14, False) == {"all_in": True}
        account = await db_manager.get_user_info(123)
        assert account["money"] == 0
        assert account["total_gain"] == 4
        assert account["total_loss"] == -14
        assert account["plays"] == 2
        assert account["bankrupt_count"] == 1

    asyncio.run(exercise())


def test_allin_uses_selected_stake_when_balance_changes(database, monkeypatch):
    async def exercise():
        await db_manager.update_user_money(123, 10)

        async def select_stake(user_id):
            account = await db_manager.get_user_info(user_id)
            await db_manager.update_user_money(user_id, 20)
            return account

        monkeypatch.setattr("cogs.gamba.get_user_info", select_stake)
        monkeypatch.setattr("cogs.gamba.random.choice", lambda odds: -1)
        ctx = SimpleNamespace(
            author=SimpleNamespace(id=123, mention="@bettor"), send=AsyncMock()
        )
        await Gamba.allin.callback(Gamba(None), ctx)
        account = await db_manager.get_user_info(123)
        assert account["money"] == 10
        assert account["total_loss"] == -10
        ctx.send.assert_awaited_once_with("@bettor lost 10 coins", delete_after=5)

    asyncio.run(exercise())


def test_failed_settlement_does_not_announce_outcome(monkeypatch):
    async def exercise():
        monkeypatch.setattr(
            "cogs.gamba.settle_wager",
            AsyncMock(side_effect=RuntimeError("database failed")),
        )
        ctx = SimpleNamespace(
            author=SimpleNamespace(id=123, mention="@bettor"), send=AsyncMock()
        )
        with pytest.raises(RuntimeError, match="database failed"):
            await Gamba(None).gamble_money(ctx, 10)
        ctx.send.assert_not_awaited()

    asyncio.run(exercise())
