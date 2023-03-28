""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
🐍 A simple template to start to code your own and personalized discord bot in Python programming language.
Version: 5.5.0
"""

from typing import List

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks


# Here we name the cog and create a new class for the cog.
class Template(commands.Cog, name="template"):
    def __init__(self, bot):
        self.bot = bot

    # Here you can just add your own commands, you'll always need to provide
    # "self" as first parameter.

    @commands.hybrid_command(
        name="testcommand",
        description="This is a testing command that does nothing.",
    )
    # This will only allow non-blacklisted members to execute the command
    @checks.not_blacklisted()
    # This will only allow owners of the bot to execute the command ->
    # config.json
    @checks.is_owner()
    async def testcommand(self, context: Context):
        """
        This is a testing command that does nothing.
        :param context: The application command context.
        """
        # Do your stuff here

        # Don't forget to remove "pass", I added this just because there's no
        # content in the method.
        pass

    # @app_commands.command()
    # @app_commands.describe(fruits='fruits to choose from')
    # @app_commands.choices(fruits=[
    #     Choice(name='apple', value=1),
    #     Choice(name='banana', value=2),
    #     Choice(name='cherry', value=3),
    # ])
    # async def fruit(interaction: discord.Interaction, fruits: Choice[int]):
    # await interaction.response.send_message(f'Your favourite fruit is
    # {fruits.name}.')

    # async def fruit_autocomplete(self,
    #     interaction: discord.Interaction,
    #     current: str,
    # ) -> List[app_commands.Choice[str]]:
    #     fruits = ['Banana', 'Pineapple', 'Apple', 'Watermelon', 'Melon', 'Cherry']
    #     return [
    #         app_commands.Choice(name=fruit, value=fruit)
    #         for fruit in fruits if current.lower() in fruit.lower()
    #     ]

    # @app_commands.command()
    # @app_commands.autocomplete(fruit=fruit_autocomplete)
    # async def fruits(self, interaction: discord.Interaction, fruit: str):
    # await interaction.response.send_message(f'Your favourite fruit seems to
    # be {fruit}')

    # async def rps_autocomplete(self,
    #     interaction: discord.Interaction,
    #     current: str,
    # ) -> List[app_commands.Choice[str]]:
    #     choices = ['Rock', 'Paper', 'Scissors']
    #     return [
    #         app_commands.Choice(name=choice, value=choice)
    #         for choice in choices if current.lower() in choice.lower()
    #     ]

    # # play rock paper scissors
    # @commands.hybrid_command(name="rp")
    # @app_commands.autocomplete(choices=rps_autocomplete)
    # async def rp(self, i: discord.Interaction, choices:str):
    #     choices = choices.lower()
    #     if (choices == 'rock'):
    #         counter = 'paper'
    #     elif (choices == 'paper'):
    #         counter = 'scissors'
    #     else:
    #         counter = 'rock'
    #     # rest of your command


# And then we finally add the cog to the bot so that it can load, unload,
# reload and use it's content.
async def setup(bot):
    await bot.add_cog(Template(bot))
