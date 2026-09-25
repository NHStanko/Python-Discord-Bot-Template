"""AI-powered Discord context-menu reactions."""

import asyncio
import json
import os
import random

import discord
from google.genai import types

from helpers.ai import load_ai_helper_from_config
from helpers.discord_context import add_message_context, extract_message_content
from helpers.image_gen import create_twitch_chat_image
from helpers.prompts import load_prompt, load_prompt_json, render_prompt
from helpers.twitch_chat import (
    apply_subscriber_badges,
    load_emote_map,
    load_loyalty_badges,
    sanitize_bajs_chat_data,
)

AI_CONTEXT_MENUS = {}


def ai_context_menu(name):
    def wrapper(func):
        AI_CONTEXT_MENUS[name] = {
            "callback": func,
            "type": discord.AppCommandType.message,
        }
        return func

    return wrapper


@ai_context_menu(name="xQc Explains")
async def xqc_explains(
    interaction: discord.Interaction, message: discord.Message
) -> None:
    """
    Generate an explanation in xQc's style for the given message content.

    Parameters:
    - interaction: The interaction that triggered this command
    - message: The message being acted upon
    """
    # Notify the user that we're processing
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Get the logger from the bot
    logger = interaction.client.logger
    logger.info(
        f"Processing xQc Explains request for message ID: {message.id} from user: {interaction.user.name}"
    )

    # Extract content from message
    (
        content_text,
        image_path,
        title,
        description,
        url,
        temp_files,
    ) = await extract_message_content(message, interaction, logger, interaction.client)

    try:
        # Load the AI helper
        ai_helper = load_ai_helper_from_config(interaction.client, logger=logger)
        if not ai_helper:
            logger.error("Failed to initialize AI helper")
            await interaction.followup.send(
                "Failed to initialize AI helper. Check your API key configuration.",
                ephemeral=True,
            )
            return

        # Prepare the prompt
        prompt = content_text
        if title:
            prompt = f"Title: {title}\n{prompt}"
        if description:
            prompt = f"{prompt}\nDescription: {description}"
        if url:
            prompt = f"{prompt}\nURL: {url}"

        # Add placeholder text if the prompt is empty to prevent API errors
        if not prompt.strip() and image_path:
            prompt = "Please explain this image."

        prompt, image_path = await add_message_context(
            message, prompt, image_path, temp_files, interaction.client, logger
        )

        logger.info("Final prompt prepared (%s characters)", len(prompt))

        # Keep the persona and safety instructions in a reviewed resource file.
        system_prompt = load_prompt("xqc_explains.txt")

        # Generate the AI response with web search enabled
        response, error = await ai_helper.generate_content(
            prompt=prompt,
            image_path=image_path,
            system_prompt=system_prompt,
            thinking_level="high",
            enable_web_search=True,  # Enable web search for latest information
        )

        if error or not response:
            logger.error(error or "AI response was empty or null")
            await interaction.followup.send(
                error or "Someone tell Nick there is a problem with the AI",
                ephemeral=True,
            )
            return

        # Create and send the embed
        embed = discord.Embed(
            description=response,
            color=0x2196F3,  # Blue color that matches xQc's branding
        )

        embed.set_author(
            name="xQc",
            icon_url="https://pbs.twimg.com/profile_images/1948335986007474176/diqK-2Jj_400x400.jpg",
        )

        await message.reply(embed=embed)
        await interaction.followup.send(
            "Explanation generated successfully!", ephemeral=True
        )

    except Exception as e:
        logger.exception(f"Error generating xQc explanation: {str(e)}")
        await interaction.followup.send(
            "An error occurred while generating the explanation. Please try again later.",
            ephemeral=True,
        )
    finally:
        # Clean up all temporary files we've created
        for temp_file in temp_files:
            if temp_file and os.path.exists(temp_file):
                try:
                    logger.info(f"Cleaning up temporary file: {temp_file}")
                    await asyncio.to_thread(os.remove, temp_file)
                except Exception as e:
                    logger.error(f"Error cleaning up temporary file {temp_file}: {e}")


@ai_context_menu(name="Bajs React")
async def test_ai(interaction: discord.Interaction, message: discord.Message) -> None:
    """
    Generate a simulated Twitch chat response based on the message content using Gemini AI.

    Parameters:
    - interaction: The interaction that triggered this command.
    - message: The message being acted upon.
    """
    # Notify the user that we're processing
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Get the logger from the bot
    logger = interaction.client.logger
    logger.info(
        f"Processing TwitchChat AI request for message ID: {message.id} from user: {interaction.user.name}"
    )

    # Load the AI helper
    ai_helper = load_ai_helper_from_config(interaction.client, logger=logger)
    if not ai_helper:
        logger.error("Failed to initialize AI helper")
        await interaction.followup.send(
            "Failed to initialize AI helper. Check your API key configuration.",
            ephemeral=True,
        )
        return

    # Initialize variables
    (
        content_text,
        image_path,
        title,
        description,
        url,
        temp_files,
    ) = await extract_message_content(message, interaction, logger, interaction.client)

    # Prepare the prompt
    prompt = content_text
    if title:
        prompt = f"Title: {title}\n{prompt}"
    if description:
        prompt = f"{prompt}\nDescription: {description}"
    if url:
        prompt = f"{prompt}\nURL: {url}"

    # Add placeholder text if the prompt is empty to prevent API errors
    if image_path and ((url and not title and not description) or not prompt.strip()):
        prompt = "Please respond to this image."

    prompt, image_path = await add_message_context(
        message, prompt, image_path, temp_files, interaction.client, logger
    )

    logger.info("Final prompt prepared (%s characters)", len(prompt))

    emote_dict = load_prompt_json("bajs_emote_weights.json")
    if not isinstance(emote_dict, dict):
        raise ValueError("Bajs emote weights must be a JSON object")

    optional_rules = []
    if random.random() < 0.25:
        optional_rules.append(
            "You have an xQc fan, also known as a juicer, in the chat."
        )
    if random.random() < 0.50:
        optional_rules.append(
            "Some user will just spam ?????? when they do not know what is going on."
        )
    if random.random() < 0.25:
        optional_rules.append(
            "You can have a user who is a stan for a specific streamer; they only use that streamer's emotes."
        )
    if random.random() < 0.25:
        optional_rules.append(
            "You should have one user with the username flickerfireheart; they are a baj and juicer and should not say offensive things."
        )
    optional_rules_text = (
        "\n".join(optional_rules) or "No extra chatter constraints apply."
    )
    system_prompt = render_prompt(
        "bajs_react.txt",
        OPTIONAL_RULES=optional_rules_text,
        EMOTE_WEIGHTS_JSON=json.dumps(
            emote_dict, ensure_ascii=False, sort_keys=True, indent=2
        ),
    )

    # Define the response schema
    response_schema = types.Schema(
        type=types.Type.OBJECT,
        required=["chats", "explanation"],
        properties={
            "explanation": types.Schema(
                type=types.Type.STRING,
                description="A brief explanation of what was observed in the content and how the AI plans to respond, 200 words max",
            ),
            "chats": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["username", "message"],
                    properties={
                        "username": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "message": types.Schema(
                            type=types.Type.STRING,
                        ),
                    },
                ),
            ),
            "deleted_count": types.Schema(
                type=types.Type.INTEGER,
                description="Number of chat entries replaced by the exact moderation placeholder",
            ),
        },
    )

    # Generate the AI response
    try:
        logger.info("Loading emotes from emotes.json")
        emote_map = await asyncio.to_thread(load_emote_map)
        logger.info(f"Loaded {len(emote_map)} emotes")

        # Now that we have the emotes loaded, we can generate the AI response with emote awareness
        available_emotes = list(emote_map.keys())

        # Generate AI response fully asynchronously
        logger.info("Generating AI response with emote awareness asynchronously...")
        response, error = await ai_helper.generate_content(
            prompt=prompt,
            image_path=image_path,
            system_prompt=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            available_emotes=available_emotes,
            thinking_level="high",
        )

        if error or not response:
            logger.error(error or "AI response was empty or null")
            await interaction.followup.send(
                error or "Tell Nick there is a problem with the AI", ephemeral=True
            )
            return

        # Parse the JSON response
        try:
            logger.info("Parsing JSON response")

            # Check if response is wrapped in markdown code blocks (```json...```)
            cleaned_response = response
            if "```json" in response:
                # Extract just the JSON part from the markdown code block
                # This regex finds content between ```json and ``` markers
                import re

                json_match = re.search(r"```json\n(.*?)```", response, re.DOTALL)
                if json_match:
                    cleaned_response = json_match.group(1)
                else:
                    # Fallback: just remove the prefix and assume the rest is JSON
                    cleaned_response = response.split("```json\n", 1)[1].rsplit(
                        "```", 1
                    )[0]
                logger.info("Extracted JSON from markdown code block")

            # Handle cases where there might be text before the JSON
            if not cleaned_response.strip().startswith("{"):
                possible_json_start = cleaned_response.find("{")
                if possible_json_start != -1:
                    cleaned_response = cleaned_response[possible_json_start:]
                    logger.info("Trimmed text before JSON object")

            chat_data = sanitize_bajs_chat_data(json.loads(cleaned_response))

            # Log the explanation if available
            if "explanation" in chat_data:
                logger.debug(
                    "AI explanation generated (%s characters)",
                    len(chat_data["explanation"]),
                )

            # Get the chats and randomize their order
            chats = chat_data.get("chats", [])

            # Assign subscriber badges to roughly half of the chatters
            badge_pool = await asyncio.to_thread(load_loyalty_badges)
            assigned_badges = apply_subscriber_badges(chats, badge_pool)
            if assigned_badges:
                logger.info(f"Assigned subscriber badges to {assigned_badges} chatters")

            random.shuffle(chats)

            # Generate the image with chat and emotes
            logger.info("Generating Twitch chat image")

            # Use asyncio.to_thread (Python 3.9+) or run_in_executor for image generation
            loop = asyncio.get_event_loop()
            result_image_path = await loop.run_in_executor(
                None,
                lambda: create_twitch_chat_image(
                    chat_data, emote_map=emote_map, line_spacing=5
                ),
            )

            if result_image_path:
                # Send the image as a reply
                await message.reply(file=discord.File(result_image_path))

                # Clean up the generated result image
                try:
                    logger.info(f"Cleaning up result image file: {result_image_path}")
                    await asyncio.to_thread(os.remove, result_image_path)
                except Exception as e:
                    logger.error(f"Error cleaning up result image file: {e}")
            else:
                logger.error("Failed to generate Twitch chat image")
                await interaction.followup.send(
                    "Failed to generate the Twitch chat image.", ephemeral=True
                )

            await interaction.followup.send(
                "Twitch chat simulation generated successfully!\n"
                f"Description: {chat_data['explanation']}\n"
                f"Messages deleted by moderator: {chat_data['deleted_count']}",
                ephemeral=True,
            )

        except json.JSONDecodeError as e:
            # Do not expose the model's invalid payload; it can contain unsafe text.
            logger.error(f"JSON decode error: {e}")
            logger.error("AI returned invalid JSON (%s characters)", len(response))
            await interaction.followup.send(
                "The AI returned an improperly formatted response. Please try again.",
                ephemeral=True,
            )

    except Exception as e:
        logger.exception(f"Error processing emotes or generating image: {str(e)}")
        await interaction.followup.send(
            "Someone tell Nick there is a problem with my AI", ephemeral=True
        )
    finally:
        # Clean up all temporary files we've created
        for temp_file in temp_files:
            if temp_file and os.path.exists(temp_file):
                try:
                    logger.info(f"Cleaning up temporary file: {temp_file}")
                    await asyncio.to_thread(os.remove, temp_file)
                except Exception as e:
                    logger.error(f"Error cleaning up temporary file {temp_file}: {e}")


async def setup(bot):
    for name, data in AI_CONTEXT_MENUS.items():
        bot.tree.remove_command(name, type=data["type"])
        command = discord.app_commands.ContextMenu(
            name=name,
            callback=data["callback"],
            type=data["type"],
        )
        bot.tree.add_command(command)


async def teardown(bot):
    for name, data in AI_CONTEXT_MENUS.items():
        bot.tree.remove_command(name, type=data["type"])
