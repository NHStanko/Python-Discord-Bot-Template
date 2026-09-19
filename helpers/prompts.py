"""Load and render prompt resources shipped with the bot."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_MARKER_PATTERN = re.compile(r"\[\[([A-Z0-9_]+)\]\]")


def _prompt_path(name: str) -> Path:
    """Return a prompt resource path while rejecting path traversal."""
    prompt_path = (PROMPTS_DIR / name).resolve()
    if PROMPTS_DIR not in prompt_path.parents:
        raise ValueError(f"Prompt resource must live under {PROMPTS_DIR}")
    return prompt_path


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a UTF-8 prompt resource independent of the process cwd."""
    return _prompt_path(name).read_text(encoding="utf-8")


def load_prompt_json(name: str) -> Any:
    """Load a JSON resource from the prompt directory."""
    return json.loads(load_prompt(name))


def render_prompt(name: str, **values: object) -> str:
    """Render explicit ``[[UPPER_SNAKE_CASE]]`` prompt markers.

    Marker replacement is deliberately narrower than ``str.format`` so prompt
    prose can contain braces without accidentally becoming a format string.
    """
    template = load_prompt(name)
    markers = set(_MARKER_PATTERN.findall(template))
    missing = markers.difference(values)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Missing prompt values: {missing_text}")

    rendered = template
    for marker in markers:
        rendered = rendered.replace(f"[[{marker}]]", str(values[marker]))

    unresolved = _MARKER_PATTERN.findall(rendered)
    if unresolved:
        unresolved_text = ", ".join(sorted(set(unresolved)))
        raise ValueError(f"Unresolved prompt markers: {unresolved_text}")
    return rendered
