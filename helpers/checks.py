"""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

from typing import Callable, TypeVar

from discord.ext import commands

from exceptions import GamblingDisabled, UserBlacklisted, UserNotOwner
from helpers import db_manager

T = TypeVar("T")


def is_owner() -> Callable[[T], T]:
    """
    This is a custom check to see if the user executing the command is an owner of the bot.
    """

    async def predicate(context: commands.Context) -> bool:
        owners = {int(owner) for owner in context.bot.config.get("owners", [])}
        if context.author.id not in owners and not await context.bot.is_owner(
            context.author
        ):
            raise UserNotOwner
        return True

    return commands.check(predicate)


def not_blacklisted() -> Callable[[T], T]:
    """
    This is a custom check to see if the user executing the command is blacklisted.
    """

    async def predicate(context: commands.Context) -> bool:
        if await db_manager.is_blacklisted(context.author.id):
            raise UserBlacklisted
        return True

    return commands.check(predicate)


def gambling_enabled() -> Callable[[T], T]:
    """
    This is a custom check to see if the gambling feature is enabled.
    """

    async def predicate(context: commands.Context) -> bool:
        if not context.bot.config.get("gambling", False):
            raise GamblingDisabled
        return True

    return commands.check(predicate)
