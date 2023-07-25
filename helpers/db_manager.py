""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

import os

import aiosqlite
import logging

DATABASE_PATH = f"{os.path.realpath(os.path.dirname(__file__))}/../database/database.db"


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
        await db.execute("INSERT INTO blacklist(user_id) VALUES (?)", (user_id,))
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
    """
    This function will keep track of the number of times a song has been played by a user
    CREATE TABLE IF NOT EXISTS `plays` (
        `id` int(11) NOT NULL,
        `user_id` varchar(20) NOT NULL,
        `song_id` varchar(20) NOT NULL,
        `times_played` int(11) NOT NULL,
        );

    """
    
    logger = logging.getLogger("discord_bot")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if the song has already been played by the user
        rows = await db.execute(
            "SELECT times_played FROM plays WHERE user_id=? AND song_id=?",
            (user_id, song),
        )
        
        # Fetch the result
        result = await rows.fetchone()
        if result is not None:
            times_played = result[0] + 1
            await db.execute(
                "UPDATE plays SET times_played=? WHERE user_id=? AND song_id=?",
                (times_played, user_id, song),
            )
            await db.commit()
            return times_played
        else:
            # If the song has not been played by the user, add it to the database
            await db.execute(
                "INSERT INTO plays(user_id, song_id, times_played) VALUES (?, ?, ?)",
                (user_id, song, 1),
            )
            await db.commit()
            return 1

async def get_plays(user_id: int, song: str) -> int:
    # check if user id is 0, if so, return the total number of times the song has been played
    if user_id == 0:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            rows = await db.execute(
                "SELECT SUM(times_played) FROM plays WHERE song_id=?",
                (   
                    song,
                ),
            )
            async with rows as cursor:
                result = await cursor.fetchone()
                return result[0] if result[0] is not None else 0
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
                return result[0] if result[0] is not None else 0
            
# List the top 10 songs played by all or a specific user
async def get_leaderboard(user_id: int ) -> list:
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
                (
                    user_id,
                ),
            )
            print(rows)
        async with rows as cursor:
            result = await cursor.fetchall()
            result_list = []
            for row in result:
                result_list.append(row)
            return result_list

        