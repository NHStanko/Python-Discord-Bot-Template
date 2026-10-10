import asyncio

import pytest

from helpers import db_manager


@pytest.fixture
def database(monkeypatch, tmp_path):
    database_path = tmp_path / "gambling.db"
    monkeypatch.setattr(db_manager, "DATABASE_PATH", str(database_path))

    asyncio.run(db_manager.init_db())
    return database_path


def test_concurrent_initialization_creates_one_account(database):
    async def exercise():
        accounts = await asyncio.gather(
            *(db_manager.get_user_info(123) for _ in range(12))
        )
        assert all(account["money"] == 10000 for account in accounts)
        async with db_manager.aiosqlite.connect(database) as db:
            async with db.execute("SELECT COUNT(*) FROM money") as cursor:
                assert (await cursor.fetchone())[0] == 1

    asyncio.run(exercise())


def test_concurrent_results_preserve_every_outcome(database):
    async def exercise():
        await db_manager.check_user(123)
        outcomes = [10, -5] * 6
        await asyncio.gather(*(db_manager.play_result(123, net) for net in outcomes))
        account = await db_manager.get_user_info(123)
        assert account["money"] == 10030
        assert account["total_gain"] == 60
        assert account["total_loss"] == -30
        assert account["plays"] == 12
        assert account["bankrupt_count"] == 0

    asyncio.run(exercise())


def test_bankruptcy_counts_only_crossing_zero(database):
    async def exercise():
        await db_manager.update_user_money(123, 10)
        for net, expected_balance, expected_count in [
            (-1, 9, 0),
            (0, 9, 0),
            (-9, 0, 1),
            (0, 0, 1),
            (-1, -1, 1),
            (11, 10, 1),
            (-11, -1, 2),
        ]:
            await db_manager.play_result(123, net)
            account = await db_manager.get_user_info(123)
            assert account["money"] == expected_balance
            assert account["bankrupt_count"] == expected_count
        assert account["plays"] == 7
        assert account["total_loss"] == -22
        assert account["total_gain"] == 11

    asyncio.run(exercise())


def test_initialization_preserves_existing_balance(database):
    async def exercise():
        await db_manager.update_user_money(123, 42)
        await asyncio.gather(*(db_manager.create_user(123) for _ in range(12)))
        assert (await db_manager.get_user_info(123))["money"] == 42

    asyncio.run(exercise())
