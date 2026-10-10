import asyncio
from pathlib import Path

import pytest

from helpers import db_manager


@pytest.fixture
def database(monkeypatch, tmp_path):
    database_path = tmp_path / "counters.db"
    monkeypatch.setattr(db_manager, "DATABASE_PATH", str(database_path))

    async def initialize():
        async with db_manager.aiosqlite.connect(database_path) as db:
            schema = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
            await db.executescript(schema.read_text())
            await db.commit()

    asyncio.run(initialize())
    return database_path


def test_concurrent_warns_receive_distinct_ids(database):
    async def exercise():
        ids = await asyncio.gather(
            *(db_manager.add_warn(123, 456, 789, f"reason {i}") for i in range(12))
        )
        assert sorted(ids) == list(range(1, 13))
        warnings = await db_manager.get_warnings(123, 456)
        assert sorted(warning[5] for warning in warnings) == list(range(1, 13))
        assert {warning[3] for warning in warnings} == {
            f"reason {i}" for i in range(12)
        }
        assert await db_manager.add_warn(123, 457, 789, "other server") == 1
        assert await db_manager.add_warn(124, 456, 789, "other user") == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("initial_plays", [0, 5])
def test_concurrent_plays_preserve_each_increment(database, initial_plays):
    async def exercise():
        for _ in range(initial_plays):
            await db_manager.add_play(123, "song")
        counts = await asyncio.gather(
            *(db_manager.add_play(123, "song") for _ in range(12))
        )
        assert sorted(counts) == list(range(initial_plays + 1, initial_plays + 13))
        assert await db_manager.get_plays(123, "song") == initial_plays + 12
        async with db_manager.aiosqlite.connect(database) as db:
            async with db.execute("SELECT COUNT(*) FROM plays") as cursor:
                assert (await cursor.fetchone())[0] == 1
        assert await db_manager.add_play(124, "song") == 1
        assert await db_manager.add_play(123, "other song") == 1
        assert await db_manager.get_plays(0, "song") == initial_plays + 13

    asyncio.run(exercise())
