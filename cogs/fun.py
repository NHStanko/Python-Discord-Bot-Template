""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.

Version: 5.5.0
"""

import random

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks


class Choice(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.blurple)
    async def confirm(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.value = "heads"
        self.stop()

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.blurple)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = "tails"
        self.stop()



class RockPaperScissors(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Scissors", description="You choose scissors.", emoji="✂"
            ),
            discord.SelectOption(
                label="Rock", description="You choose rock.", emoji="🪨"
            ),
            discord.SelectOption(
                label="paper", description="You choose paper.", emoji="🧻"
            ),
        ]
        super().__init__(
            placeholder="Choose...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        choices = {
            "rock": 0,
            "paper": 1,
            "scissors": 2,
        }
        user_choice = self.values[0].lower()
        user_choice_index = choices[user_choice]

        bot_choice = random.choice(list(choices.keys()))
        bot_choice_index = choices[bot_choice]

        result_embed = discord.Embed(color=0x9C84EF)
        result_embed.set_author(
            name=interaction.user.name, icon_url=interaction.user.avatar.url
        )

        if user_choice_index == bot_choice_index:
            result_embed.description = f"**That's a draw!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
            result_embed.colour = 0xF59E42
        elif user_choice_index == 0 and bot_choice_index == 2:
            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
            result_embed.colour = 0x9C84EF
        elif user_choice_index == 1 and bot_choice_index == 0:
            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
            result_embed.colour = 0x9C84EF
        elif user_choice_index == 2 and bot_choice_index == 1:
            result_embed.description = f"**You won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
            result_embed.colour = 0x9C84EF
        else:
            result_embed.description = (
                f"**I won!**\nYou've chosen {user_choice} and I've chosen {bot_choice}."
            )
            result_embed.colour = 0xE02B2B
        await interaction.response.edit_message(
            embed=result_embed, content=None, view=None
        )


class RockPaperScissorsView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(RockPaperScissors())


class Fun(commands.Cog, name="fun"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="randomfact", description="Get a random fact.")
    @checks.not_blacklisted()
    async def randomfact(self, context: Context) -> None:
        """
        Get a random fact.

        :param context: The hybrid command context.
        """
        # This will prevent your bot from stopping everything when doing a web
        # request - see:
        # https://discordpy.readthedocs.io/en/stable/faq.html#how-do-i-make-a-web-request
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://uselessfacts.jsph.pl/random.json?language=en"
            ) as request:
                if request.status == 200:
                    data = await request.json()
                    embed = discord.Embed(description=data["text"], color=0xD75BF4)
                else:
                    embed = discord.Embed(
                        title="Error!",
                        description="There is something wrong with the API, please try again later",
                        color=0xE02B2B,
                    )
                await context.send(embed=embed)

    @commands.hybrid_command(
        name="coinflip", description="Make a coin flip, but give your bet before."
    )
    @checks.not_blacklisted()
    async def coinflip(self, context: Context) -> None:
        """
        Make a coin flip, but give your bet before.

        :param context: The hybrid command context.
        """
        buttons = Choice()
        embed = discord.Embed(description="What is your bet?", color=0x9C84EF)
        message = await context.send(embed=embed, view=buttons)
        await buttons.wait()  # We wait for the user to click a button.
        result = random.choice(["heads", "tails"])
        if buttons.value == result:
            embed = discord.Embed(
                description=f"Correct! You guessed `{buttons.value}` and I flipped the coin to `{result}`.",
                color=0x9C84EF,
            )
        else:
            embed = discord.Embed(
                description=f"Woops! You guessed `{buttons.value}` and I flipped the coin to `{result}`, better luck next time!",
                color=0xE02B2B,
            )
        await message.edit(embed=embed, view=None, content=None)

    @commands.hybrid_command(
        name="rps", description="Play the rock paper scissors game against the bot."
    )
    @checks.not_blacklisted()
    async def rock_paper_scissors(self, context: Context) -> None:
        """
        Play the rock paper scissors game against the bot.

        :param context: The hybrid command context.
        """
        view = RockPaperScissorsView()
        await context.send("Please make your choice", view=view)
    # Response : Weight

    @commands.hybrid_command(description="Chat with forsen like a chatter", name="forsen")
    async def forsen(self, ctx: Context) -> None:
        test = random.randint(1, 10)
        if test == 1:
            await ctx.send("*generating god seed*")
        elif test == 2:
            await ctx.send("fuck")
        elif test == 3:
            await ctx.send("OOOOOOOO")
        elif test == 4:
            await ctx.send("*swedish mumbles*")
        else:
            pass

    # sex update
    @commands.hybrid_command(
        name="sex",
        description="Sex Update"
    )
    async def sex(self, context: Context) -> None:
        # Send button
        view = Sex_Update()
        await context.send(view=view)
    
    @commands.hybrid_command(
        name="addsex",
        description="Add to sex"
    )
    async def moresex(self, context: Context, more: str) -> None:
        # add more to sex_responses
        global sex_responses
        sex_responses[more] = 1
        await context.send(f"{more} added", ephemeral=True, delete_after=5)
        print(f"{more} added")
    
    @commands.hybrid_command(
        name="purgebot",
        description="Remove all messages from the bot"
    )
    async def purgebot(self, context: Context, count: int = 100) -> None:
        # Loop through the last count messages and delete any from the bot 
        async for message in context.channel.history(limit=count):
            if message.author == self.bot.user:
                await message.delete()
        await context.send(f"Deleted {count} messages", ephemeral=True, delete_after=5)
    
sex_responses = {
    "Sex": 5,
    "Seggs": 5,
    "No Sex": 5,
    "Fortnite sex confirmed": 1,
    "https://i.kym-cdn.com/photos/images/original/002/250/727/781.jpg": 1,
    "Heavy update releasing tomorrow, now featuring sex with Sasha": 1,
    "https://i.kym-cdn.com/photos/images/original/002/250/424/3eb.jpg": 1,
    "Amogus sex confirmed": 1,
    "Suisex": 1,
    "https://www.youtube.com/watch?v=SXWDcivD188": 1,
    "Minecraft sex update confirmed sauce https://www.youtube.com/watch?v=SXWDcivD188": 1,
    "https://fxtwitter.com/ULTRAKILLGame/status/1600549517853704192": 1,
    "buttplug.io support coming in sex update 2": 1,
    "https://preview.redd.it/10w4ih7rm3z81.jpg?width=640&crop=smart&auto=webp&v=enabled&s=7ca43518d0b8e1f9798b0be00c0577edbbf25756": 1,
    "No war thunder sex update https://preview.redd.it/cdayyf4jndk91.jpg?width=640&crop=smart&auto=webp&v=enabled&s=872b759d7aad274d02cb7d257358494bda0f0070" : 1,
    "If this so called “sex” (though, as a Redditor, I am unsure what the definition of “sex” is or how to partake in said “sex”) were to be added to the game, it’ll probably be the next top tier 12.0 rank VIII premium pre-order addition costing $60+ along with a shitty decal and title…exclusively for the American tree.": 1,
    "https://i.kym-cdn.com/photos/images/newsfeed/001/842/713/b73.jpg": 5,
    "Victoria 3 segggs??? https://i.imgur.com/50I4er5.png": 1,
    "Stellaris sex update https://pm1.narvii.com/7868/2d433f9e7960782db5f1c813bdb7e70e8a4fe636r1-1920-1080v2_hq.jpg": 1,
    "https://preview.redd.it/2sdb1z49nvz81.png?width=960&crop=smart&auto=webp&v=enabled&s=a146d07239d359e609f9155793250f8196dd2f66": 1,
    ":flushed:": 1,
    ":regional_indicator_s: :regional_indicator_e: :regional_indicator_x:": 5,
    "<:Lolice:522562117153456170>": 3,
    "<:perrypoint:1071144019394048001> This one right here officer": 1,
    "<:udyr:471352514999222272>": 1,
    "<:shyblush:1071146264739196958>": 3,
    "<:kobold:1004220228785422406> <:kobold:1004220228785422406> <:kobold:1004220228785422406>" : 1,
    "<:no:458523435438571538>": 3,
    "Big booba fortnite": 1,
    "When that roblox sex update fr fr": 1,
    "I was offered sex today, with a 21 year old girl. In exchange for that, I was supposed to advertise some kind of e-betting website to my friends. Of course I declined because I am a person of high moral standards with a strong willpower. Just as strong as Ebettle, the best betting website on the internet. Now available for children.": 1,
    "my girlfriend wont stop using a miku voice during sex. the entire time, for every noise she makes. its a really great impression, dont get me wrong, but theres a time and a place. at first, it was a little funny, but she keeps on doing it. every. time. i love her a lot, and our relationship is perfect otherwise, so i really dont want to have to break up with her over this, but its getting so bad that ive contemplated it.has anyone experienced something similar? what should i do about it?" : 1,
    "get it 😍😍 the joke is that 🤯🤯🤯🤯 the woman is about to lift her shirt🤯🤯😰😼😼😼😼 but the video 📼📼📼 cuts ✂️✂️✂️to something else,2,2,2,1,?1?1!1!1!1!1😅😅😅😅😅😅😅the joke, is sex!1!1!1!1!1!1! 😼😼😼😼😼😼 i cant believe op trolled🧌🧌🧌🧌🧌me like that!1!1!1 i literally had my dick 🍆🍆🍆💦💦💦💦in my hand ✊✊✊✊✊✊what a silly goober‼️❗️‼️❗️‼️❗️‼️‼️‼️‼️❕‼️❕‼️‼️‼️‼️❗️❗️‼️‼️‼️💥💥💥❗️‼️❗️❗️‼️‼️‼️🇧🇩🇧🇩🇧🇩💥" :2,
    "Anyway, how's your sex life": 1,
    
}
    
class Sex_Update(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=36000)
        self.value = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @discord.ui.button(label='Sex Update', style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Load sex_responses into a list with the weight of each response
        # being the number of times it appears in the list.
        
        users = ["157644363227201536"]
        # If user is in users list, 10% change to respond differently
        if str(interaction.user.id) in users:
            if random.randint(1, 10) == 1:
                await interaction.response.send_message(f":middle_finger:", delete_after=60)
                return
        
        weighted_responses = []
        for key, value in sex_responses.items():
            weighted_responses.extend([key] * value)
        
        await interaction.response.send_message(f"{interaction.user.mention}\n{random.choice(weighted_responses)}", delete_after=60)



    
async def setup(bot):
    await bot.add_cog(Fun(bot))
    
