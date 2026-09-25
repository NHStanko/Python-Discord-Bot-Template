"""Async OpenAI-compatible text, vision, structured output, and search."""

import asyncio
import base64
import io
import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from PIL import Image


class AIHelper:
    def __init__(
        self, bot, api_key: str, model: str, logger=None,
        debug_mode: bool = False, base_url: str = "https://openrouter.ai/api/v1",
        web_search: str = "auto", structured_output: str = "json_schema",
        reasoning_effort: str | None = None, search_model: str | None = None,
        provider: str | None = None, provider_fallbacks: bool = True,
    ):
        self.bot = bot
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("ai_base_url must be an HTTP(S) API base URL")
        if web_search not in {"auto", "openrouter", "openai", "off"}:
            raise ValueError("Invalid ai_web_search setting")
        if structured_output not in {"json_schema", "json_object", "prompt"}:
            raise ValueError("Invalid ai_structured_output setting")
        if provider is not None:
            if not isinstance(provider, str) or not provider.strip():
                raise ValueError("ai_provider must be a nonempty OpenRouter provider slug")
            if parsed.hostname != "openrouter.ai":
                raise ValueError("ai_provider requires an OpenRouter API base URL")
            provider = provider.strip()
        if not isinstance(provider_fallbacks, bool):
            raise ValueError("ai_provider_fallbacks must be a boolean")
        if not provider_fallbacks and provider is None:
            raise ValueError("ai_provider_fallbacks=false requires ai_provider")
        self.provider = provider
        self.provider_fallbacks = provider_fallbacks
        self.web_search = web_search
        if web_search == "auto":
            self.web_search = {
                "openrouter.ai": "openrouter", "api.openai.com": "openai",
            }.get(parsed.hostname, "unsupported")
        self.structured_output = structured_output
        self.reasoning_effort = reasoning_effort
        self.search_model = search_model or model
        self.logger = logger or logging.getLogger("discord_bot")
        self.debug_mode = debug_mode
        self._http_session = None
        self._http_session_lock = asyncio.Lock()

    async def _get_http_session(self):
        async with self._http_session_lock:
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()
            return self._http_session

    async def close(self):
        async with self._http_session_lock:
            if self._http_session is not None and not self._http_session.closed:
                await self._http_session.close()
            self._http_session = None

    async def download_image(self, url):
        path = None
        try:
            session = await self._get_http_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                content = await response.read()
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            await asyncio.to_thread(Path(path).write_bytes, content)
            return path
        except Exception:
            if path:
                Path(path).unlink(missing_ok=True)
            self.logger.warning("Could not download AI input image")
            return None

    @staticmethod
    def _image_url(path):
        # Decode actual bytes: downloads may have a .png name but contain a GIF.
        # Send the first frame of animated images, supported across vision APIs.
        with Image.open(path) as image:
            output = io.BytesIO()
            image.convert("RGB").save(output, format="PNG")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    async def _post(self, endpoint, payload):
        session = await self._get_http_session()
        async with session.post(
            f"{self.base_url}/{endpoint}", json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=aiohttp.ClientTimeout(total=180),
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                # Provider error bodies can echo private input; do not expose them.
                self.logger.warning("AI request failed (HTTP %s)", response.status)
                if response.status == 429:
                    return None, "AI rate limit or quota reached. Please try again later."
                if response.status in {401, 403}:
                    return None, "AI authentication or access failed. Check the API key and model access."
                if response.status in {400, 404, 422}:
                    return None, "AI request rejected. Check the endpoint, model, and its support for images, structured output, reasoning, and web search."
                return None, f"AI service request failed (HTTP {response.status}). Please try again later."
            data = await response.json()
            if data.get("error"):
                return None, "AI provider returned an error. Check model availability and account limits."
            return data, None

    async def generate_content(
        self, prompt, image_path=None, system_prompt=None, response_mime_type=None,
        response_schema=None, available_emotes=None,
        enable_web_search=False,
    ):
        """Return (text, error); unsupported features are never silently retried."""
        try:
            search = enable_web_search and self.web_search != "off"
            if search and self.web_search == "unsupported":
                return None, "Web search is not configured for this endpoint. Set ai_web_search to openrouter, openai, or off."
            responses = search and self.web_search == "openai"
            instructions = system_prompt or ""
            if available_emotes:
                instructions += "\nAvailable emotes: " + json.dumps(available_emotes)
            format_spec = None
            if response_schema or response_mime_type == "application/json":
                instructions += "\nReturn only a JSON object."
                if response_schema:
                    instructions += "\nRequired JSON schema: " + json.dumps(response_schema)
                if self.structured_output == "json_schema" and response_schema:
                    format_spec = {
                        "type": "json_schema", "name": "response",
                        "strict": True, "schema": response_schema,
                    }
                elif self.structured_output != "prompt":
                    format_spec = {"type": "json_object"}
            content = [{"type": "input_text" if responses else "text",
                        "text": prompt or "Please analyze this content."}]
            if image_path:
                try:
                    image_url = await asyncio.to_thread(self._image_url, image_path)
                except (OSError, ValueError):
                    return None, "Could not read the image for AI analysis."
                content.append(
                    {"type": "input_image", "image_url": image_url} if responses else
                    {"type": "image_url", "image_url": {"url": image_url}}
                )
            payload = {"model": self.search_model if search else self.model}
            # Reasoning is opt-in since many otherwise compatible models reject it.
            effort = self.reasoning_effort
            if responses:
                payload.update(input=[{"role": "user", "content": content}],
                               instructions=instructions, tools=[{"type": "web_search"}])
                if format_spec:
                    payload["text"] = {"format": format_spec}
                if effort:
                    payload["reasoning"] = {"effort": effort}
            else:
                if self.provider is not None:
                    payload["provider"] = {
                        "order": [self.provider],
                        "allow_fallbacks": self.provider_fallbacks,
                    }
                payload["messages"] = [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": content},
                ]
                if format_spec:
                    if format_spec["type"] == "json_schema":
                        payload["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {k: v for k, v in format_spec.items() if k != "type"},
                        }
                    else:
                        payload["response_format"] = format_spec
                if effort:
                    payload["reasoning_effort"] = effort
                if search:
                    payload["plugins"] = [{"id": "web"}]
            if self.debug_mode:
                self.logger.debug("AI model=%s search=%s structured=%s image=%s",
                                  payload["model"], bool(search), bool(format_spec), bool(image_path))
            data, error = await self._post("responses" if responses else "chat/completions", payload)
            if error:
                return None, error
            if responses:
                if data.get("status") in {"failed", "incomplete"}:
                    return None, "AI response was incomplete. Please try again."
                parts = [part for item in data.get("output", []) if item.get("type") == "message"
                         for part in item.get("content", [])]
                refused = any(part.get("type") == "refusal" for part in parts)
                text = "\n".join(part["text"] for part in parts if part.get("type") == "output_text")
            else:
                choices = data.get("choices") or []
                choice = choices[0] if choices else {}
                message = choice.get("message") or {}
                refused = message.get("refusal") or choice.get("finish_reason") == "content_filter"
                if choice.get("finish_reason") == "length":
                    return None, "AI response was cut off by the model's output limit. Try a shorter request."
                text = message.get("content")
            if refused:
                return None, "The selected AI model declined this request."
            if not isinstance(text, str) or not text.strip():
                return None, "AI returned an empty response. Try another model or request."
            return text, None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None, "Could not reach the AI service or the request timed out. Please try again."
        except Exception as error:
            self.logger.warning("AI request failed (%s)", type(error).__name__)
            return None, "AI request failed. Check the model and API configuration."


async def close_ai_helpers(bot):
    cache = getattr(bot, "_ai_helper_cache", {})
    helpers = list(cache.values())
    cache.clear()
    for helper in helpers:
        await helper.close()


def load_ai_helper_from_config(bot, config_path="config/config.json", logger=None):
    logger = logger or logging.getLogger("discord_bot")
    try:
        if config_path == "config/config.json" and hasattr(bot, "config"):
            config = bot.config
        else:
            config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        options = {
            "api_key": config.get("ai_api_key") or os.getenv("AI_API_KEY"),
            "model": config.get("ai_model"),
            "base_url": config.get("ai_base_url") or "https://openrouter.ai/api/v1",
            "web_search": config.get("ai_web_search", "auto"),
            "structured_output": config.get("ai_structured_output", "json_schema"),
            "reasoning_effort": config.get("ai_reasoning_effort") or None,
            "search_model": config.get("ai_search_model") or None,
            "provider": config.get("ai_provider") or None,
            "provider_fallbacks": config.get("ai_provider_fallbacks", True),
            "debug_mode": config.get("ai_debug", False),
        }
        if not options["api_key"] or not options["model"]:
            logger.error("Configure ai_api_key (or AI_API_KEY) and ai_model to enable AI")
            return None
        cache = getattr(bot, "_ai_helper_cache", None)
        if cache is None:
            cache = bot._ai_helper_cache = {}
        key = (str(config_path), *options.values())
        if key not in cache:
            cache[key] = AIHelper(bot, logger=logger, **options)
        return cache[key]
    except Exception as error:
        logger.error("Could not load AI configuration (%s)", type(error).__name__)
        return None
