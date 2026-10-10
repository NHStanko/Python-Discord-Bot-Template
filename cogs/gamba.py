import random

from discord import Embed, User
from discord.ext import commands

from helpers import checks
from helpers.db_manager import (
    get_user_info,
    settle_wager,
    update_user_money,
)


class Gamba(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def gamble_money(self, ctx, amount: int | None):
        try:
            result = await settle_wager(
                ctx.author.id, amount, random.choice((True, False))
            )
        except ValueError as exc:
            await ctx.send(str(exc), delete_after=5)
            return
        outcome = "won" if result["net"] > 0 else "lost"
        prefix = "went all in and " if result["all_in"] else ""
        await ctx.send(
            f"{ctx.author.mention} {prefix}{outcome} {result['amount']} coins",
            delete_after=None if result["all_in"] else 5,
        )

    @commands.hybrid_command(brief="Gamba your money", name="gamba")
    @checks.gambling_enabled()
    async def gamba(self, ctx, amount: int):
        await self.gamble_money(ctx, amount)

    @commands.hybrid_command(brief="Gamba all your money", name="allin")
    @checks.gambling_enabled()
    async def allin(self, ctx):
        await self.gamble_money(ctx, None)

    @commands.hybrid_group(name="casino", brief="Casino commands")
    async def casino(self, ctx):
        await ctx.send("Casino commands", delete_after=5)

    @casino.command(brief="Get your win and loss stats", name="stats")
    @checks.gambling_enabled()
    async def casino_stats(self, ctx, hide: bool = True, user: User = None):
        if user is None:
            user = ctx.author
        user_info = await get_user_info(user.id)
        # infinite ratio
        ratio = (
            (user_info["total_gain"] / (user_info["total_loss"] * -1)) * 100
            if user_info["total_loss"] != 0
            else "N/A"
        )
        plays = user_info["plays"]
        bankrupt_count = user_info["bankrupt_count"]
        # create an embed
        embed = Embed(
            title="Casino Stats",
            description=f"Stats for {user.mention}",
            color=0x00FF00,
        )
        embed.add_field(name="Money", value=f"{user_info['money']} coins")
        embed.add_field(name="Gain", value=f"{user_info['total_gain']} coins")
        embed.add_field(name="Loss", value=f"{user_info['total_loss']} coins")
        embed.add_field(name="Return Ratio", value=f"{ratio}%")
        embed.add_field(name="Total Plays", value=f"{plays}")
        embed.add_field(name="Bankruptcies", value=f"{bankrupt_count}")
        await ctx.send(embed=embed, ephemeral=hide)

    @casino.command(brief="Set your money", name="set")
    @checks.is_owner()
    @checks.gambling_enabled()
    async def casino_set(self, ctx, amount: int, user: User = None):
        if user is None:
            user = ctx.author
        await update_user_money(user.id, amount)
        await ctx.send(f"Set {user.mention}'s money to {amount}", delete_after=5)

    @casino.command(brief="Balance of your money", name="balance")
    @checks.gambling_enabled()
    async def casino_balance(self, ctx, user: User = None, hide: bool = True):
        if user is None:
            user = ctx.author
        money = await get_user_info(user.id)
        await ctx.send(
            f"{user.mention} has {money['money']} coins", delete_after=5, ephemeral=hide
        )


async def setup(bot):
    await bot.add_cog(Gamba(bot))
