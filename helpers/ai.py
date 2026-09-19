import asyncio
import inspect
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from google import genai
from google.genai import types


class AIHelper:
    def __init__(
        self,
        bot,
        api_key: str,
        model: str = "gemini-1.5-flash-002",
        logger=None,
        debug_mode: bool = False,
    ):
        """Initialize the AI helper with API key and model"""
        self.bot = bot
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.logger = logger or logging.getLogger("discord_bot")
        self.debug_mode = debug_mode
        self._http_session: aiohttp.ClientSession | None = None
        self._http_session_lock: asyncio.Lock | None = None
        self._debug_lock = asyncio.Lock()
        if debug_mode:
            self.debug_folder = Path("debug")
            self.debug_file = self.debug_folder / "debug.json"

    async def _get_http_session(self) -> aiohttp.ClientSession:
        session = self._http_session
        if session is not None and not session.closed:
            return session

        if self._http_session_lock is None:
            self._http_session_lock = asyncio.Lock()
        async with self._http_session_lock:
            session = self._http_session
            if session is None or session.closed:
                session = aiohttp.ClientSession()
                self._http_session = session
            return session

    async def close(self) -> None:
        """Close network clients owned by this helper.

        The installed Gemini SDK exposes no public ``Client.close`` method;
        close its underlying sync HTTP client when available, while keeping
        the cleanup best-effort across SDK versions.
        """
        if self._http_session_lock is None:
            session = self._http_session
            self._http_session = None
            if session is not None and not session.closed:
                await session.close()
        else:
            async with self._http_session_lock:
                session = self._http_session
                self._http_session = None
                if session is not None and not session.closed:
                    await session.close()

        api_client = getattr(self.client, "_api_client", None)
        http_client = getattr(api_client, "_httpx_client", None)
        close = getattr(http_client, "close", None)
        if callable(close):
            await asyncio.to_thread(close)

    def _save_debug_info_sync(self, request_data: Dict[str, Any]) -> None:
        self.debug_folder.mkdir(exist_ok=True)
        if not self.debug_file.exists():
            self.debug_file.write_text(json.dumps({"requests": []}), encoding="utf-8")
        debug_data = json.loads(self.debug_file.read_text(encoding="utf-8"))
        request_data["timestamp"] = datetime.now().isoformat()
        debug_data["requests"].append(request_data)
        self.debug_file.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")

    async def _save_debug_info(self, request_data: Dict[str, Any]) -> None:
        """Save debug information to debug.json"""
        if not self.debug_mode:
            return

        try:
            async with self._debug_lock:
                await asyncio.to_thread(self._save_debug_info_sync, request_data)
            self.logger.info("Debug information saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving debug information: {e}")

    async def download_image(self, url: str) -> Optional[str]:
        """Download an image from a URL and save it to a temporary file"""
        try:
            self.logger.info("Downloading remote image")

            # Set up headers to mimic a real browser request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            session = await self._get_http_session()
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    self.logger.error(
                        f"Failed to download image: HTTP {response.status}"
                    )
                    return None

                # Create a temporary file
                content = await response.read()
                fd, temp_path = await asyncio.to_thread(tempfile.mkstemp, suffix=".png")
                os.close(fd)
                await asyncio.to_thread(Path(temp_path).write_bytes, content)

                self.logger.info(f"Image downloaded and saved to: {temp_path}")
                return temp_path
        except Exception as e:
            self.logger.error(f"Error downloading image: {e}")
            return None

    async def upload_file(self, file_path: str) -> Optional[Any]:
        """Upload a file to the Gemini API asynchronously"""
        try:
            self.logger.info(f"Uploading file to Gemini API: {file_path}")
            # Run the synchronous file upload in an executor
            file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            self.logger.info(f"File uploaded successfully. URI: {file.uri}")
            return file
        except Exception as e:
            self.logger.error(f"Error uploading file: {e}")
            return None

    async def generate_content(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[types.Schema] = None,
        available_emotes: Optional[List[str]] = None,
        safety_settings: Optional[List[Dict]] = None,
        include_thoughts: bool = False,
        thinking_level: Optional[str] = None,
        enable_web_search: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Generate content using the Gemini API asynchronously.

        Args:
            prompt: The text prompt to send to the model
            image_path: Optional path to an image file to include with the prompt
            system_prompt: Optional system prompt to set context for the model
            response_mime_type: Optional MIME type for the response format
            response_schema: Optional schema to structure the response
            available_emotes: Optional list of available emotes for chat simulations
            safety_settings: Optional safety settings for content generation
            include_thoughts: Whether to include model thinking in the response
            thinking_level: Optional model reasoning level (minimal, low, medium, or high)
            enable_web_search: Whether to enable Google search tool for web lookups

        Returns:
            Tuple of (response_text, error_message). Only one will be non-None.
        """
        uploaded_file_name: str | None = None
        try:
            # Prepare debug data if debug mode is enabled
            debug_data = {
                "input": {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "image_path": image_path,
                    "response_mime_type": response_mime_type,
                    "available_emotes": available_emotes,
                    "enable_web_search": enable_web_search,
                }
            }

            # Prepare parts and config
            parts = []
            image_added = False

            # Add image if provided
            if image_path:
                self.logger.info(f"Processing image for Gemini API: {image_path}")
                try:
                    file = await self.upload_file(image_path)
                    if file:
                        uploaded_file_name = getattr(file, "name", None)
                        parts.append(
                            types.Part.from_uri(
                                file_uri=file.uri,
                                mime_type=file.mime_type,
                            )
                        )
                        self.logger.info(
                            f"Added image to prompt with mime_type: {file.mime_type}"
                        )
                        image_added = True

                        # Copy image to debug folder if debug mode is enabled
                        if self.debug_mode:
                            debug_image_path = (
                                self.debug_folder
                                / f"debug_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            )
                            await asyncio.to_thread(
                                shutil.copy2, image_path, debug_image_path
                            )
                            debug_data["input"]["debug_image_path"] = str(
                                debug_image_path
                            )
                    else:
                        self.logger.warning(
                            "Failed to upload image, continuing with text-only request"
                        )
                except Exception as e:
                    self.logger.error(f"Error adding image to prompt: {e}")
                    self.logger.warning("Continuing with text-only request")

            # Add prompt text
            if prompt:
                self.logger.info("Adding text prompt (%s characters)", len(prompt))
                parts.append(types.Part.from_text(text=prompt))
            elif not image_added:
                # If there's no prompt and image upload failed, add a default prompt
                default_prompt = "Please analyze this content."
                self.logger.info(f"Adding default text prompt: {default_prompt}")
                parts.append(types.Part.from_text(text=default_prompt))

            # Ensure parts list is not empty
            if not parts:
                self.logger.error("No content parts available for the request")
                return None, "No content was available for the AI request."

            # Create content
            contents = [
                types.Content(
                    role="user",
                    parts=parts,
                ),
            ]

            # Generate content config
            # Gemini 3.x models use thinking levels and no longer recommend
            # sampling parameters such as temperature.
            config_kwargs = {}
            if not self.model.startswith("gemini-3"):
                config_kwargs["temperature"] = 0.7
            generate_content_config = types.GenerateContentConfig(**config_kwargs)

            # Set up thinking config if requested. include_thoughts controls
            # returned thought summaries; thinking_level controls reasoning effort.
            if include_thoughts or thinking_level:
                thinking = types.ThinkingConfig(
                    include_thoughts=include_thoughts,
                    thinking_level=thinking_level,
                )
                generate_content_config.thinking_config = thinking

            # Add web search tool if enabled
            if enable_web_search:
                self.logger.info("Enabling Google Search tool")
                tools = [
                    types.Tool(google_search=types.GoogleSearch()),
                ]
                generate_content_config.tools = tools

                # Web search works best with more recent model versions
                if not self.model.startswith(
                    (
                        "gemini-1.5-pro",
                        "gemini-1.5-flash-latest",
                        "gemini-2",
                        "gemini-3",
                    )
                ):
                    self.logger.warning(
                        f"Web search works best with newer models. Current model: {self.model}. "
                        "Consider using gemini-1.5-pro or newer."
                    )

            # Add response mime type if provided
            if response_mime_type:
                self.logger.info(f"Setting response MIME type: {response_mime_type}")
                generate_content_config.response_mime_type = response_mime_type

            # Add response schema if provided
            if response_schema:
                self.logger.info("Setting response schema for structured output")
                generate_content_config.response_schema = response_schema

            # Add system prompt if provided, possibly with emote information
            if system_prompt:
                modified_system_prompt = system_prompt

                self.logger.info(
                    "Setting system prompt (%s characters)", len(modified_system_prompt)
                )
                generate_content_config.system_instruction = [
                    types.Part.from_text(text=modified_system_prompt),
                ]

            # Generate content asynchronously using run_in_executor
            self.logger.info(f"Sending request to Gemini API using model: {self.model}")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents,
                config=generate_content_config,
            )
            self.logger.debug("Received response object from Gemini API")

            self.logger.info("Received response from Gemini API")

            response_text = getattr(response, "text", "")

            # Handle blank responses from the API
            if not response_text or not response_text.strip():
                message = (
                    "The Gemini API returned an empty response. This might happen if the free tier limit "
                    "was reached or the service had trouble generating a reply."
                )
                self.logger.error(message)
                if self.debug_mode:
                    debug_data["error"] = message
                    await self._save_debug_info(debug_data)
                return None, message

            # Save debug information if debug mode is enabled
            if self.debug_mode:
                debug_data["output"] = {
                    "text": response_text,
                    "model": self.model,
                    "response_dict": await asyncio.to_thread(response.to_json_dict),
                }
                await self._save_debug_info(debug_data)

            return response_text, None
        except Exception as e:
            message = str(e)
            self.logger.error(f"Error generating content: {message}")

            user_message = "Gemini API error."
            lowered = message.lower()
            if "quota" in lowered or "rate limit" in lowered or "429" in lowered:
                user_message = "Gemini free API usage limit or rate limit reached. Please try again later."
            elif not message.strip():
                user_message = "Gemini API returned a blank error. Please try again."
            else:
                # Keep the message short for the user
                user_message = f"Gemini error: {message.splitlines()[0]}"

            if self.debug_mode:
                debug_data["error"] = message
                await self._save_debug_info(debug_data)

            return None, user_message
        finally:
            if uploaded_file_name:
                await self._delete_uploaded_file(uploaded_file_name)

    async def _delete_uploaded_file(self, name: str) -> None:
        delete = getattr(getattr(self.client, "files", None), "delete", None)
        if not callable(delete):
            self.logger.debug("Gemini SDK does not expose remote file deletion")
            return
        try:
            result = await asyncio.to_thread(delete, name=name)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self.logger.warning(
                "Could not delete temporary Gemini file %s", name, exc_info=True
            )


_AI_HELPER_CACHE_ATTRIBUTE = "_ai_helper_cache"


async def close_ai_helpers(bot) -> None:
    """Close and clear AI helpers cached on a bot instance."""
    cache = getattr(bot, _AI_HELPER_CACHE_ATTRIBUTE, None)
    if not cache:
        return
    helpers = list(cache.values())
    cache.clear()
    for helper in helpers:
        try:
            await helper.close()
        except Exception:
            helper.logger.exception("Could not close cached AI helper")


# Helper function to load the AI helper from config
def load_ai_helper_from_config(
    bot, config_path: str = "config/config.json", logger=None
) -> Optional[AIHelper]:
    """Load AI helper from config file"""
    try:
        if logger:
            logger.info(f"Loading AI helper from config: {config_path}")

        if config_path == "config/config.json" and hasattr(bot, "config"):
            config = bot.config
        else:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)

        api_key = config.get("gemini_api_key")
        model = config.get("gemini_model") or "gemini-1.5-flash-002"
        debug_mode = config.get("gemini_debug", False)

        if not api_key:
            if logger:
                logger.error("No Gemini API key found in config")
            print("No Gemini API key found in config")
            return None

        if logger:
            logger.info(
                f"AI helper initialized with model: {model}, debug mode: {debug_mode}"
            )

        cache = getattr(bot, _AI_HELPER_CACHE_ATTRIBUTE, None)
        if cache is None:
            cache = {}
            setattr(bot, _AI_HELPER_CACHE_ATTRIBUTE, cache)
        cache_key = (str(config_path), api_key, model, debug_mode)
        helper = cache.get(cache_key)
        if helper is None:
            helper = AIHelper(
                bot=bot,
                api_key=api_key,
                model=model,
                logger=logger,
                debug_mode=debug_mode,
            )
            cache[cache_key] = helper
        return helper
    except Exception as e:
        if logger:
            logger.error(f"Error loading AI helper from config: {e}")
        print(f"Error loading AI helper from config: {e}")
        return None
