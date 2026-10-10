"""Load and validate bot settings without import-time I/O."""

import json
from copy import deepcopy
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config/config.json"
AI_DEFAULTS = {
    "max_concurrent_requests": 32,
    "max_image_bytes": 20 * 1024 * 1024,
    "max_image_pixels": 40_000_000,
}


def validate_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    config = deepcopy(config)
    for key in ("prefix", "token"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"Configuration '{key}' must be a nonempty string")
    for key, default in (
        ("sync_commands_globally", True),
        ("gambling", False),
        ("gemini_debug", False),
        ("reddit_api_enabled", False),
    ):
        config.setdefault(key, default)
        if not isinstance(config[key], bool):
            raise ValueError(f"Configuration '{key}' must be a boolean")
    owners = config.setdefault("owners", [])
    if not isinstance(owners, list):
        raise ValueError("Configuration 'owners' must be a list of user IDs")
    try:
        if any(
            isinstance(owner, bool) or not str(owner).isdigit() or int(owner) <= 0
            for owner in owners
        ):
            raise ValueError
        config["owners"] = [int(owner) for owner in owners]
    except (TypeError, ValueError):
        raise ValueError(
            "Configuration 'owners' must contain positive user IDs"
        ) from None
    ai = config.setdefault("ai", {})
    if not isinstance(ai, dict):
        raise ValueError("Configuration 'ai' must be an object")
    for key, default in AI_DEFAULTS.items():
        ai.setdefault(key, default)
        if type(ai[key]) is not int or ai[key] < 1:
            raise ValueError(f"Configuration 'ai.{key}' must be a positive integer")
    tts = config.setdefault("tts", {})
    if not isinstance(tts, dict):
        raise ValueError("Configuration 'tts' must be an object")
    for key in ("cpu_threads", "max_attachment_bytes", "max_samples_per_voice"):
        if key in tts and (type(tts[key]) is not int or tts[key] < 1):
            raise ValueError(f"Configuration 'tts.{key}' must be a positive integer")
    return config


def load_config(path=None) -> dict:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"Configuration file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in configuration at line {exc.lineno}"
        ) from None
    return validate_config(config)
