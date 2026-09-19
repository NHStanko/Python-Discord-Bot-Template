"""Helpers for Twitch chat rendering and moderation data."""

import json
import math
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMOTES_DIR = PROJECT_ROOT / "emotes"
EMOTES_CONFIG = EMOTES_DIR / "emotes.json"
LOYALTY_BADGE_DIR = EMOTES_DIR / "22484632" / "loyalty"

__all__ = [
    "DELETED_CHAT_PLACEHOLDER",
    "apply_subscriber_badges",
    "load_emote_map",
    "load_loyalty_badges",
    "sanitize_bajs_chat_data",
]


def load_loyalty_badges(base_path: Path = LOYALTY_BADGE_DIR):
    badges_by_tier = {1: [], 2: [], 3: []}
    if not base_path.exists():
        return badges_by_tier

    try:
        for entry in sorted(base_path.iterdir()):
            if entry.suffix.lower() != ".png":
                continue
            try:
                badge_id = int(entry.stem)
            except ValueError:
                continue

            if badge_id >= 3000:
                tier = 3
            elif badge_id >= 2000:
                tier = 2
            else:
                tier = 1

            months = badge_id % 100
            badges_by_tier[tier].append(
                {
                    "path": str(entry),
                    "months": months,
                    "tier": tier,
                }
            )
    except OSError:
        return badges_by_tier

    for tier in badges_by_tier:
        badges_by_tier[tier].sort(key=lambda item: item["months"])

    return badges_by_tier


def weighted_choice(choices, weights):
    total = sum(weights)
    if total <= 0:
        return None

    pick = random.random() * total
    cumulative = 0.0
    for choice, weight in zip(choices, weights):
        cumulative += weight
        if pick <= cumulative:
            return choice
    return choices[-1]


def pick_badge_for_viewer(badge_pool):
    tier_weights = [(1, 16), (2, 4), (3, 1)]
    available = [
        (tier, weight) for tier, weight in tier_weights if badge_pool.get(tier)
    ]
    if not available:
        return None

    tiers, weights = zip(*available)
    tier_choice = weighted_choice(tiers, weights)
    if tier_choice is None:
        return None

    entries = badge_pool[tier_choice]
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]

    decay = 0.65
    exp_weights = [math.pow(decay, idx) for idx, _ in enumerate(entries)]
    selection = weighted_choice(entries, exp_weights)
    return selection or entries[0]


def apply_subscriber_badges(chats, badge_pool):
    if not chats or not any(badge_pool.values()):
        return 0

    applied = 0
    for chat in chats:
        if random.random() >= (1 / 3):
            continue

        badge = pick_badge_for_viewer(badge_pool)
        if not badge:
            break

        chat["subscriber_badge"] = badge["path"]
        chat["subscriber_tier"] = badge["tier"]
        chat["subscriber_months"] = badge["months"]
        applied += 1

    return applied


def load_emote_map() -> dict[str, str]:
    """Load emote metadata from disk without relying on the process cwd."""
    emotes_data = json.loads(EMOTES_CONFIG.read_text(encoding="utf-8"))
    emote_map: dict[str, str] = {}

    for emotes in emotes_data.get("global", {}).values():
        for emote_name, emote_path in emotes.items():
            emote_map[emote_name] = str(EMOTES_DIR / emote_path)

    for channel_data in emotes_data.get("subscriber_emotes", {}).values():
        for source, emotes in channel_data.items():
            if source == "loyalty_badges":
                continue
            for emote_name, emote_path in emotes.items():
                emote_map[emote_name] = str(EMOTES_DIR / emote_path)

    return emote_map


DELETED_CHAT_PLACEHOLDER = "message deleted by moderator"


def sanitize_bajs_chat_data(chat_data: object) -> dict:
    """Keep model-generated chat data safe to render and send.

    The model must never return the original text behind a moderation
    placeholder. Only the redacted placeholder and a derived count leave this
    boundary.
    """
    if not isinstance(chat_data, dict):
        raise ValueError("AI response must be a JSON object")

    raw_chats = chat_data.get("chats")
    if not isinstance(raw_chats, list):
        raise ValueError("AI response must contain a chats array")

    chats = []
    deleted_count = 0
    for raw_chat in raw_chats:
        if not isinstance(raw_chat, dict):
            continue
        username = raw_chat.get("username", "Unknown")
        message = raw_chat.get("message", "")
        username = username if isinstance(username, str) else str(username)
        message = message if isinstance(message, str) else str(message)
        if DELETED_CHAT_PLACEHOLDER in message.casefold():
            message = DELETED_CHAT_PLACEHOLDER
            deleted_count += 1
        chats.append({"username": username[:20], "message": message})

    explanation = chat_data.get("explanation", "")
    explanation = explanation if isinstance(explanation, str) else str(explanation)
    return {
        "chats": chats,
        "explanation": explanation,
        "deleted_count": deleted_count,
    }
