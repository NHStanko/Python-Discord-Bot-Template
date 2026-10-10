"""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

import os
from pathlib import Path

import aiosqlite

DATABASE_PATH = f"{os.path.realpath(os.path.dirname(__file__))}/../database/database.db"


async def init_db() -> None:
    """Create tables and migrate legacy data before enabling unique indexes.

    Conflicting legacy balances need operator reconciliation: never guess which
    monetary record is correct. All migration changes roll back on failure.
    """
    schema = Path(__file__).resolve().parent.parent / "database/schema.sql"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(schema.read_text(encoding="utf-8"))
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS bot_migrations (version INTEGER PRIMARY KEY)"
            )
            async with db.execute(
                "SELECT 1 FROM bot_migrations WHERE version=1"
            ) as cursor:
                migrated = await cursor.fetchone()
            if not migrated:
                async with db.execute(
                    "SELECT user_id FROM (SELECT DISTINCT user_id, money, total_loss, "
                    "total_gain, bankrupt_count, plays FROM money) "
                    "GROUP BY user_id HAVING COUNT(*) > 1"
                ) as cursor:
                    if await cursor.fetchone():
                        raise RuntimeError(
                            "Conflicting duplicate money records; reconcile balances before restarting. Migration rolled back."
                        )
                await db.execute(
                    "DELETE FROM money WHERE rowid NOT IN (SELECT MIN(rowid) FROM money GROUP BY user_id)"
                )
                await db.execute(
                    "DELETE FROM blacklist WHERE rowid NOT IN (SELECT MIN(rowid) FROM blacklist GROUP BY user_id)"
                )
                await db.execute(
                    "UPDATE plays SET times_played=(SELECT SUM(p.times_played) FROM plays p WHERE p.user_id=plays.user_id AND p.song_id=plays.song_id) WHERE id IN (SELECT MIN(id) FROM plays GROUP BY user_id, song_id)"
                )
                await db.execute(
                    "DELETE FROM plays WHERE id NOT IN (SELECT MIN(id) FROM plays GROUP BY user_id, song_id)"
                )
                # Preserve warning contents and existing IDs wherever possible.
                async with db.execute(
                    "SELECT rowid, id, user_id, server_id FROM warns ORDER BY user_id, server_id, id, rowid"
                ) as cursor:
                    warnings = await cursor.fetchall()
                maxima = {}
                for _, warn_id, user_id, server_id in warnings:
                    key = (user_id, server_id)
                    maxima[key] = max(maxima.get(key, 0), warn_id)
                seen = set()
                for rowid, warn_id, user_id, server_id in warnings:
                    key = (user_id, server_id)
                    identity = (*key, warn_id)
                    if identity in seen:
                        maxima[key] += 1
                        await db.execute(
                            "UPDATE warns SET id=? WHERE rowid=?", (maxima[key], rowid)
                        )
                    seen.add(identity)
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS money_user ON money(user_id)"
                )
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS blacklist_user ON blacklist(user_id)"
                )
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS plays_user_song ON plays(user_id, song_id)"
                )
                await db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS warns_user_server_id ON warns(user_id, server_id, id)"
                )
                await db.execute("INSERT INTO bot_migrations VALUES (1)")
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


async def get_blacklisted_users() -> list:
    """
    This function will return the list of all blacklisted users.

    :param user_id: The ID of the user that should be checked.
    :return: True if the user is blacklisted, False if not.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT user_id, strftime('%s', created_at) FROM blacklist"
        ) as cursor:
            result = await cursor.fetchall()
            return result


async def is_blacklisted(user_id: int) -> bool:
    """
    This function will check if a user is blacklisted.

    :param user_id: The ID of the user that should be checked.
    :return: True if the user is blacklisted, False if not.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT * FROM blacklist WHERE user_id=?", (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result is not None


async def add_user_to_blacklist(user_id: int) -> int:
    """
    This function will add a user based on its ID in the blacklist.

    :param user_id: The ID of the user that should be added into the blacklist.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO blacklist(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        await db.commit()
        rows = await db.execute("SELECT COUNT(*) FROM blacklist")
        async with rows as cursor:
            result = await cursor.fetchone()
            return result[0] if result is not None else 0


async def remove_user_from_blacklist(user_id: int) -> int:
    """
    This function will remove a user based on its ID from the blacklist.

    :param user_id: The ID of the user that should be removed from the blacklist.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM blacklist WHERE user_id=?", (user_id,))
        await db.commit()
        rows = await db.execute("SELECT COUNT(*) FROM blacklist")
        async with rows as cursor:
            result = await cursor.fetchone()
            return result[0] if result is not None else 0


async def add_warn(user_id: int, server_id: int, moderator_id: int, reason: str) -> int:
    """
    This function will add a warn to the database.

    :param user_id: The ID of the user that should be warned.
    :param reason: The reason why the user should be warned.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        rows = await db.execute(
            "SELECT id FROM warns WHERE user_id=? AND server_id=? ORDER BY id DESC LIMIT 1",
            (
                user_id,
                server_id,
            ),
        )
        async with rows as cursor:
            result = await cursor.fetchone()
            warn_id = result[0] + 1 if result is not None else 1
            await db.execute(
                "INSERT INTO warns(id, user_id, server_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?)",
                (
                    warn_id,
                    user_id,
                    server_id,
                    moderator_id,
                    reason,
                ),
            )
            await db.commit()
            return warn_id


async def remove_warn(warn_id: int, user_id: int, server_id: int) -> int:
    """
    This function will remove a warn from the database.

    :param warn_id: The ID of the warn.
    :param user_id: The ID of the user that was warned.
    :param server_id: The ID of the server where the user has been warned
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM warns WHERE id=? AND user_id=? AND server_id=?",
            (
                warn_id,
                user_id,
                server_id,
            ),
        )
        await db.commit()
        rows = await db.execute(
            "SELECT COUNT(*) FROM warns WHERE user_id=? AND server_id=?",
            (
                user_id,
                server_id,
            ),
        )
        async with rows as cursor:
            result = await cursor.fetchone()
            return result[0] if result is not None else 0


async def get_warnings(user_id: int, server_id: int) -> list:
    """
    This function will get all the warnings of a user.

    :param user_id: The ID of the user that should be checked.
    :param server_id: The ID of the server that should be checked.
    :return: A list of all the warnings of the user.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        rows = await db.execute(
            "SELECT user_id, server_id, moderator_id, reason, strftime('%s', created_at), id FROM warns WHERE user_id=? AND server_id=?",
            (
                user_id,
                server_id,
            ),
        )
        async with rows as cursor:
            result = await cursor.fetchall()
            result_list = []
            for row in result:
                result_list.append(row)
            return result_list


async def add_play(user_id: int, song: str) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO plays(user_id, song_id, times_played) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, song_id) DO UPDATE SET times_played=times_played+1",
            (user_id, song),
        )
        # Read before commit while this transaction still owns the write lock.
        async with db.execute(
            "SELECT times_played FROM plays WHERE user_id=? AND song_id=?",
            (user_id, song),
        ) as cursor:
            result = await cursor.fetchone()
        await db.commit()
        return result[0]


async def get_plays(user_id: int, song: str) -> int:
    # check if user id is 0, if so, return the total number of times the song has been played
    if user_id == 0:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            rows = await db.execute(
                "SELECT SUM(times_played) FROM plays WHERE song_id=?",
                (song,),
            )
            async with rows as cursor:
                result = await cursor.fetchone()
                if result is None or result[0] is None:
                    return 0
                return result[0]
    else:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            rows = await db.execute(
                "SELECT times_played FROM plays WHERE user_id=? AND song_id=?",
                (
                    user_id,
                    song,
                ),
            )
            async with rows as cursor:
                result = await cursor.fetchone()
                if result is None or result[0] is None:
                    return 0
                return result[0]


# List the top 10 songs played by all or a specific user
async def get_leaderboard(user_id: int) -> list:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id == 0:
            # Combine plays for all users
            rows = await db.execute(
                "SELECT song_id, SUM(times_played) FROM plays GROUP BY song_id ORDER BY SUM(times_played) DESC LIMIT 12",
            )
        else:
            # Combine plays for a specific user, only return song_id and times_played
            rows = await db.execute(
                "SELECT song_id, times_played FROM plays WHERE user_id=? ORDER BY times_played DESC LIMIT 12",
                (user_id,),
            )
            print(rows)
        async with rows as cursor:
            result = await cursor.fetchall()
            result_list = []
            for row in result:
                result_list.append(row)
            return result_list


async def user_exists(user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        rows = await db.execute(
            "SELECT * FROM money WHERE user_id=?",
            (user_id,),
        )
        async with rows as cursor:
            result = await cursor.fetchone()
            return result is not None


async def create_user(user_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO money (user_id, money) VALUES (?, ?) ON CONFLICT(user_id) DO NOTHING",
            (
                user_id,
                10000,
            ),
        )
        await db.commit()


async def check_user(user_id: int) -> None:
    await create_user(user_id)


async def get_user_info(user_id: int) -> dict:
    await check_user(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        rows = await db.execute(
            "SELECT * FROM money WHERE user_id=?",
            (user_id,),
        )
        async with rows as cursor:
            result = await cursor.fetchone()
            if result is not None:
                return {
                    "user_id": result[0],
                    "money": result[1],
                    "total_loss": result[2],
                    "total_gain": result[3],
                    "bankrupt_count": result[4],
                    "plays": result[5],
                }
            else:
                return None


async def update_user_info(
    user_id: int,
    money: int,
    total_loss: int,
    total_gain: int,
    bankrupt_count: int,
    plays: int,
) -> None:
    await check_user(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE money SET money=?, total_loss=?, total_gain=?, bankrupt_count=?, plays=? WHERE user_id=?",
            (
                money,
                total_loss,
                total_gain,
                bankrupt_count,
                plays,
                user_id,
            ),
        )
        await db.commit()


async def update_user_money(user_id: int, money: int) -> None:
    await check_user(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE money SET money=? WHERE user_id=?",
            (
                money,
                user_id,
            ),
        )
        await db.commit()


class InsufficientFunds(ValueError):
    pass


async def settle_wager(user_id: int, amount: int | None, won: bool) -> dict:
    """Validate and settle one wager in a transaction; None wagers the balance."""
    if amount is not None and amount < 1:
        raise ValueError("You can't gamble less than 1 coin")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT INTO money(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        async with db.execute(
            "SELECT money FROM money WHERE user_id=?", (user_id,)
        ) as cursor:
            balance = (await cursor.fetchone())[0]
        wager = balance if amount is None else amount
        if wager < 1:
            raise ValueError("You can't gamble less than 1 coin")
        if wager > balance:
            raise InsufficientFunds("You don't have enough coins to gamble that much")
        net = wager if won else -wager
        await db.execute(
            "UPDATE money SET money=money+?, total_loss=total_loss+?, "
            "total_gain=total_gain+?, bankrupt_count=bankrupt_count+?, plays=plays+1 WHERE user_id=?",
            (
                net,
                min(net, 0),
                max(net, 0),
                int(balance > 0 and balance + net == 0),
                user_id,
            ),
        )
        await db.commit()
        return {
            "amount": wager,
            "net": net,
            "all_in": wager == balance,
            "money": balance + net,
        }
