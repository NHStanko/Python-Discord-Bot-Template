import os
import json
import tempfile
import logging
import aiohttp
import asyncio
from pathlib import Path
from google import genai
from google.genai import types
from typing import List, Dict, Any, Optional, Union

class AIHelper:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash-002", logger=None):
        """Initialize the AI helper with API key and model"""
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.logger = logger or logging.getLogger("discord_bot")
    
    async def download_image(self, url: str) -> Optional[str]:
        """Download an image from a URL and save it to a temporary file"""
        try:
            self.logger.info(f"Downloading image from URL: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
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
                        safety_settings: Optional[List[Dict]] = None) -> Optional[str]:
        """Generate content using the Gemini API asynchronously"""
        try:
            # Prepare parts and config
            parts = []
            
            # Add image if provided
            if image_path:
                self.logger.info(f"Processing image for Gemini API: {image_path}")
                file = await self.upload_file(image_path)
                if file:
                    parts.append(
                        types.Part.from_uri(
                            file_uri=file.uri,
                            mime_type=file.mime_type,
                        )
                    )
                    self.logger.info(f"Added image to prompt with mime_type: {file.mime_type}")
            
            # Add prompt text
            if prompt:
                self.logger.info(f"Adding text prompt: {prompt}")
                parts.append(types.Part.from_text(text=prompt))
            
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
                
                # If available_emotes is provided, add it to the system prompt
                if available_emotes and len(available_emotes) > 0:
                    # Select a random subset of emotes to show as examples (max 20)
                    import random
                    sample_size = min(20, len(available_emotes))
                    emote_examples = random.sample(available_emotes, sample_size)
                    
                    emote_info = "\n\nHere are some available emotes you can use in the messages:\n"
                    emote_info += ", ".join(emote_examples)
                    emote_info += "\n\nTry to use these emotes in your responses where appropriate."
                    
                    modified_system_prompt += emote_info
                
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
            
            self.logger.info(f"Received response from Gemini API")
            return response.text
        except Exception as e:
            self.logger.error(f"Error generating content: {e}")
            return None

# Helper function to load the AI helper from config
def load_ai_helper_from_config(config_path: str = "config/config.json", logger=None) -> Optional[AIHelper]:
    """Load AI helper from config file"""
    try:
        if logger:
            logger.info(f"Loading AI helper from config: {config_path}")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        api_key = config.get("gemini_api_key")
        model = config.get("gemini_model", "gemini-1.5-flash-002")
        
        if not api_key:
            if logger:
                logger.error("No Gemini API key found in config")
            print("No Gemini API key found in config")
            return None
        
        if logger:
            logger.info(f"AI helper initialized with model: {model}")
        
        return AIHelper(api_key=api_key, model=model, logger=logger)
    except Exception as e:
        if logger:
            logger.error(f"Error loading AI helper from config: {e}")
        print(f"Error loading AI helper from config: {e}")
        return None
