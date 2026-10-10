import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.gamba import Gamba


def test_wager_commits_before_announcement(monkeypatch):
    events = []

    async def settle(user_id, amount, won):
        events.append("committed")
        return {"net": -10, "amount": 10, "all_in": False}

    async def send(*args, **kwargs):
        assert events == ["committed"]
        events.append("sent")

    monkeypatch.setattr("cogs.gamba.settle_wager", settle)
    ctx = SimpleNamespace(author=SimpleNamespace(id=1, mention="user"), send=send)
    asyncio.run(Gamba(None).gamble_money(ctx, 10))
    assert events == ["committed", "sent"]


def test_database_failure_does_not_announce_result(monkeypatch):
    monkeypatch.setattr(
        "cogs.gamba.settle_wager",
        AsyncMock(side_effect=RuntimeError("database failed")),
    )
    ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())
    with pytest.raises(RuntimeError):
        asyncio.run(Gamba(None).gamble_money(ctx, 10))
    ctx.send.assert_not_awaited()
