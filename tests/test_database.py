import asyncio
import sqlite3
from pathlib import Path

import pytest

from helpers import db_manager as db


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(path))
    asyncio.run(db.init_db())
    return path


def test_concurrent_user_creation_and_plays(database):
    async def exercise():
        await asyncio.gather(*(db.check_user(1) for _ in range(15)))
        counts = await asyncio.gather(*(db.add_play(1, "song") for _ in range(15)))
        assert sorted(counts) == list(range(1, 16))
        assert await db.get_plays(1, "song") == 15
        await asyncio.gather(*(db.add_user_to_blacklist(1) for _ in range(10)))
        assert len(await db.get_blacklisted_users()) == 1

    asyncio.run(exercise())
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM money").fetchone()[0] == 1


def test_concurrent_warnings_have_distinct_ids(database):
    async def exercise():
        ids = await asyncio.gather(*(db.add_warn(1, 2, 3, "reason") for _ in range(15)))
        assert sorted(ids) == list(range(1, 16))

    asyncio.run(exercise())


def test_concurrent_wagers_cannot_overspend(database):
    async def exercise():
        await db.update_user_money(1, 100)
        results = await asyncio.gather(
            *(db.settle_wager(1, 100, False) for _ in range(10)), return_exceptions=True
        )
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(result is None for result in results) == 9
        info = await db.get_user_info(1)
        assert info["money"] == 0
        assert info["plays"] == 1
        assert info["bankrupt_count"] == 1

    asyncio.run(exercise())


def test_concurrent_wins_preserve_every_increment(database):
    async def exercise():
        await asyncio.gather(*(db.settle_wager(1, 10, True) for _ in range(15)))
        info = await db.get_user_info(1)
        assert info["money"] == 10150
        assert info["total_gain"] == 150
        assert info["plays"] == 15

    asyncio.run(exercise())


def test_bankruptcy_requires_balance_to_reach_zero(database):
    async def exercise():
        await db.update_user_money(1, 100)
        await db.settle_wager(1, 10, False)
        assert (await db.get_user_info(1))["bankrupt_count"] == 0
        result = await db.settle_wager(1, 90, False)
        assert result == {"all_in": True}
        info = await db.get_user_info(1)
        assert info["bankrupt_count"] == 1
        assert info["total_loss"] == -100
        for amount in (0, -1):
            with pytest.raises(ValueError):
                await db.settle_wager(1, amount, True)
        assert await db.get_user_info(1) == info

    asyncio.run(exercise())


def legacy_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(Path("database/schema.sql").read_text())
    return connection


def test_legacy_migration_preserves_counts_and_warnings(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(path))
    with legacy_database(path) as connection:
        connection.executescript("""
            INSERT INTO money(user_id) VALUES ('1'), ('1');
            INSERT INTO blacklist(user_id) VALUES ('1'), ('1');
            INSERT INTO plays(user_id, song_id, times_played) VALUES ('1', 'song', 2), ('1', 'song', 3);
            INSERT INTO warns(id, user_id, server_id, moderator_id, reason) VALUES
                (1, '1', '2', '3', 'first'), (1, '1', '2', '3', 'second'), (2, '1', '2', '3', 'third');
        """)
    asyncio.run(db.init_db())
    asyncio.run(db.init_db())  # Migration is idempotent.
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM money").fetchone()[0] == 1
        assert connection.execute("SELECT times_played FROM plays").fetchall() == [(5,)]
        assert connection.execute(
            "SELECT id, reason FROM warns ORDER BY id"
        ).fetchall() == [(1, "first"), (2, "third"), (3, "second")]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO money(user_id) VALUES ('1')")


def test_conflicting_legacy_balances_abort_migration(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DATABASE_PATH", str(path))
    with legacy_database(path) as connection:
        connection.executescript(
            "INSERT INTO money(user_id,money) VALUES ('1',100), ('1',200)"
        )
    with pytest.raises(RuntimeError, match="Conflicting duplicate money"):
        asyncio.run(db.init_db())
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT money FROM money ORDER BY money"
        ).fetchall() == [(100,), (200,)]
