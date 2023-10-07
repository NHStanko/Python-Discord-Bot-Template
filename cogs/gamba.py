import random
from discord.ext import commands
from helpers import checks
from discord import User, Embed
from helpers.db_manager import get_user_info, play_result, update_user_info, update_user_money

class Gamba(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def gamble_money(self,ctx,amount: int, hide : bool = True):
        user_info = await get_user_info(ctx.author.id)
        if amount < 1:
            await ctx.send("You can't gamble less than 1 coin")
            return
        if amount > user_info["money"]:
            await ctx.send("You don't have enough coins to gamble that much", delete_after=5)
            return
        # set to the amount of money from the result
        odds = [-1,1]
        result = random.choice(odds) * amount
        
        # all in
        if amount == user_info["money"]:
            if result < 0:
                await ctx.send(f"{ctx.author.mention} went all in and lost {amount} coins")
            else:
                await ctx.send(f"{ctx.author.mention} went all in and won {amount} coins")
        else:
            if result < 0:
                await ctx.send(f"{ctx.author.mention} lost {amount} coins", delete_after=5)
            else:
                await ctx.send(f"{ctx.author.mention} won {amount} coins", delete_after=5)
        await play_result(ctx.author.id, result)
            


    
        
    @commands.hybrid_command(brief="Gamba your money", name="gamba")
    @checks.gambling_enabled()
    async def gamba(self, ctx, amount: int):
        await self.gamble_money(ctx, amount)
        
    @commands.hybrid_command(brief="Gamba all your money", name="allin")
    @checks.gambling_enabled()
    async def allin(self, ctx):
        money = await get_user_info(ctx.author.id)
        await self.gamble_money(ctx, money["money"])
        
    @commands.hybrid_group(name="casino", brief="Casino commands")
    async def casino(self, ctx):
        await ctx.send("Casino commands", delete_after=5)
        
    @casino.command(brief="Get your win and loss stats", name="stats")
    @checks.gambling_enabled()
    async def casino_stats(self, ctx, hide : bool = True, user : User = None):
        if user is None:
            user = ctx.author
        user_info = await get_user_info(user.id)
        net = user_info["total_gain"] + user_info["total_loss"]
        # infinite ratio
        ratio = (user_info["total_gain"] / (user_info["total_loss"]*-1))*100 if user_info["total_loss"] != 0 else "N/A"
        plays = user_info["plays"]
        bankrupt_count = user_info["bankrupt_count"]
        # create an embed
        embed = Embed(title="Casino Stats", description=f"Stats for {user.mention}", color=0x00ff00)
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
    async def casino_balance(self, ctx, user: User = None, hide : bool = True):
        if user is None:
            user = ctx.author
        money = await get_user_info(user.id)
        await ctx.send(f"{user.mention} has {money['money']} coins", delete_after=5, ephemeral=hide)
        
    


async def setup(bot):
    await bot.add_cog(Gamba(bot))