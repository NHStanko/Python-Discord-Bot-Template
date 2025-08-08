import os
import json
import tempfile
import logging
import aiohttp
import asyncio
import shutil
import re
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types
from typing import List, Dict, Any, Optional, Union



class AIHelper:
    def __init__(self, bot, api_key: str, model: str = "gemini-1.5-flash-002", logger=None, debug_mode: bool = False):
        """Initialize the AI helper with API key and model"""
        self.bot = bot
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.logger = logger or logging.getLogger("discord_bot")
        self.debug_mode = debug_mode
        if debug_mode:
            self.debug_folder = Path("debug")
            self.debug_file = self.debug_folder / "debug.json"
            self.debug_folder.mkdir(exist_ok=True)
            if not self.debug_file.exists():
                with open(self.debug_file, 'w') as f:
                    json.dump({"requests": []}, f)
    
    async def _save_debug_info(self, request_data: Dict[str, Any]) -> None:
        """Save debug information to debug.json"""
        if not self.debug_mode:
            return
            
        try:
            # Load existing debug data
            with open(self.debug_file, 'r') as f:
                debug_data = json.load(f)
            
            # Add timestamp to request data
            request_data['timestamp'] = datetime.now().isoformat()
            
            # Add to requests array
            debug_data['requests'].append(request_data)
            
            # Save back to file
            with open(self.debug_file, 'w') as f:
                json.dump(debug_data, f, indent=2)
                
            self.logger.info("Debug information saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving debug information: {e}")
    
    async def download_image(self, url: str) -> Optional[str]:
        """Download an image from a URL and save it to a temporary file"""
        try:
            self.logger.info(f"Downloading image from URL: {url}")
            
            # Set up headers to mimic a real browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        self.logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
                    
                    # Create a temporary file
                    fd, temp_path = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    
                    # Save the content to the file
                    with open(temp_path, 'wb') as f:
                        f.write(await response.read())
                    
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
            loop = asyncio.get_event_loop()
            file = await loop.run_in_executor(None, lambda: self.client.files.upload(file=file_path))
            self.logger.info(f"File uploaded successfully. URI: {file.uri}")
            return file
        except Exception as e:
            self.logger.error(f"Error uploading file: {e}")
            return None
    
    async def generate_content(self, 
                        prompt: str, 
                        image_path: Optional[str] = None,
                        system_prompt: Optional[str] = None,
                        response_mime_type: Optional[str] = None,
                        response_schema: Optional[types.Schema] = None,
                        available_emotes: Optional[List[str]] = None,
                        safety_settings: Optional[List[Dict]] = None,
                        include_thoughts: bool = False,
                        enable_web_search: bool = False) -> Optional[str]:
        """Generate content using the Gemini API asynchronously
        
        Args:
            prompt: The text prompt to send to the model
            image_path: Optional path to an image file to include with the prompt
            system_prompt: Optional system prompt to set context for the model
            response_mime_type: Optional MIME type for the response format
            response_schema: Optional schema to structure the response
            available_emotes: Optional list of available emotes for chat simulations
            safety_settings: Optional safety settings for content generation
            include_thoughts: Whether to include model thinking in the response
            enable_web_search: Whether to enable Google search tool for web lookups
        """
        try:
            # Prepare debug data if debug mode is enabled
            debug_data = {
                "input": {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "image_path": image_path,
                    "response_mime_type": response_mime_type,
                    "available_emotes": available_emotes,
                    "enable_web_search": enable_web_search
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
                        parts.append(
                            types.Part.from_uri(
                                file_uri=file.uri,
                                mime_type=file.mime_type,
                            )
                        )
                        self.logger.info(f"Added image to prompt with mime_type: {file.mime_type}")
                        image_added = True
                        
                        # Copy image to debug folder if debug mode is enabled
                        if self.debug_mode:
                            debug_image_path = self.debug_folder / f"debug_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            shutil.copy2(image_path, debug_image_path)
                            debug_data["input"]["debug_image_path"] = str(debug_image_path)
                    else:
                        self.logger.warning("Failed to upload image, continuing with text-only request")
                except Exception as e:
                    self.logger.error(f"Error adding image to prompt: {e}")
                    self.logger.warning("Continuing with text-only request")
            
            # Add prompt text
            if prompt:
                self.logger.info(f"Adding text prompt: {prompt}")
                parts.append(types.Part.from_text(text=prompt))
            elif not image_added:
                # If there's no prompt and image upload failed, add a default prompt
                default_prompt = "Please analyze this content."
                self.logger.info(f"Adding default text prompt: {default_prompt}")
                parts.append(types.Part.from_text(text=default_prompt))
            
            # Ensure parts list is not empty
            if not parts:
                self.logger.error("No content parts available for the request")
                return None
            
            # Create content
            contents = [
                types.Content(
                    role="user",
                    parts=parts,
                ),
            ]
            
            # Generate content config
            generate_content_config = types.GenerateContentConfig(
                temperature=0.7,
            )
            
            # Set up thinking config if requested
            if include_thoughts:
                thinking = types.ThinkingConfig(include_thoughts=include_thoughts)
                generate_content_config.thinking_config = thinking
            
            # Add web search tool if enabled
            if enable_web_search:
                self.logger.info("Enabling Google Search tool")
                tools = [
                    types.Tool(google_search=types.GoogleSearch()),
                ]
                generate_content_config.tools = tools
                
                # Web search works best with more recent model versions
                if not self.model.startswith(("gemini-1.5-pro", "gemini-1.5-flash-latest", "gemini-2")):
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
                
                self.logger.info(f"Setting system prompt: {modified_system_prompt[:100]}...")
                generate_content_config.system_instruction = [
                    types.Part.from_text(text=modified_system_prompt),
                ]
            
            # Generate content asynchronously using run_in_executor
            self.logger.info(f"Sending request to Gemini API using model: {self.model}")
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=generate_content_config,
                )
            )
            self.logger.debug(f"Received response from Gemini API: {dir(response)}")
            self.logger.debug(f"Dumped response pydantic {response.to_json_dict()}")
            
            self.logger.info(f"Received response from Gemini API")
            
            # Save debug information if debug mode is enabled
            if self.debug_mode:
                debug_data["output"] = {
                    "text": response.text,
                    "model": self.model,
                    "response_dict": response.to_json_dict()
                }
                await self._save_debug_info(debug_data)
            
            return response.text
        except Exception as e:
            self.logger.error(f"Error generating content: {e}")
            if self.debug_mode:
                debug_data["error"] = str(e)
                await self._save_debug_info(debug_data)
            return None

# Helper function to load the AI helper from config
def load_ai_helper_from_config(bot, config_path: str = "config/config.json", logger=None) -> Optional[AIHelper]:
    """Load AI helper from config file"""
    try:
        if logger:
            logger.info(f"Loading AI helper from config: {config_path}")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        api_key = config.get("gemini_api_key")
        model = config.get("gemini_model", "gemini-1.5-flash-002")
        include_thoughts = config.get("gemini_include_thoughts", False)
        debug_mode = config.get("gemini_debug", False)
        
        if not api_key:
            if logger:
                logger.error("No Gemini API key found in config")
            print("No Gemini API key found in config")
            return None
        
        if logger:
            logger.info(f"AI helper initialized with model: {model}, debug mode: {debug_mode}")
        
        return AIHelper(bot=bot, api_key=api_key, model=model, logger=logger, debug_mode=debug_mode)
    except Exception as e:
        if logger:
            logger.error(f"Error loading AI helper from config: {e}")
        print(f"Error loading AI helper from config: {e}")
        return None
