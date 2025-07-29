import re
from typing import Callable, Pattern, Any, List, Optional
from discord import Message
import discord.utils

class MessageHandler:
    def __init__(
        self,
        func: Callable[[Message], Any],
        user_ids: Optional[List[int]] = None,
        username_pattern: Optional[Pattern] = None,
        content_pattern: Optional[Pattern] = None
    ):
        self.func = func
        self.user_ids = user_ids
        self.username_pattern = username_pattern
        self.content_pattern = content_pattern

    def matches(self, message: Message) -> bool:
        if self.user_ids and message.author.id not in self.user_ids:
            return False
        if self.username_pattern and not self.username_pattern.search(message.author.name):
            return False
        if self.content_pattern and not self.content_pattern.search(message.content):
            return False
        return True

# Registry of all handlers\
_registry: List[MessageHandler] = []



def register_message_handler(
    *,
    user_ids: Optional[List[int]] = None,
    username_regex: Optional[str] = None,
    content_regex: Optional[str] = None
) -> Callable:
    """
    Decorator to register a message handler with optional filters:
      - user_ids: list of Discord user IDs
      - username_regex: regex string to match author.name
      - content_regex: regex string to match message.content
    """
    def decorator(func: Callable[[Message], Any]) -> Callable[[Message], Any]:
        uname_pat = re.compile(username_regex) if username_regex else None
        cont_pat = re.compile(content_regex) if content_regex else None
        handler = MessageHandler(func, user_ids, uname_pat, cont_pat)
        _registry.append(handler)
        return func
    return decorator


async def process_message(message: Message) -> None:
    """
    Iterate through registered handlers and execute those whose filters match the message.
    """
    for handler in _registry:
        if handler.matches(message):
            await handler.func(message)
            
            
