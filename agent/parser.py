"""Helpers to parse structured actions from LLM output."""

from __future__ import annotations

import json
import re
from typing import Any


def _extract_markdown_json_block(text: str) -> str | None:
    """Extract JSON from ```json ... ``` blocks."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _extract_json_object(text: str) -> str | None:
    """Return the first balanced JSON object found in text."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


def parse_action(text: str) -> Any | None:
    """Parse a JSON action from raw LLM text, tolerating Chain of Thought.

    Strategy:
    1. Try exact match (json.loads).
    2. Try extracting ```json blocks.
    3. Try finding the first balanced {...} block.
    """
    if not isinstance(text, str):
        return None

    cleaned = text.strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    markdown_block = _extract_markdown_json_block(cleaned)
    if markdown_block:
        try:
            return json.loads(markdown_block)
        except Exception:
            pass

    candidate = _extract_json_object(cleaned)
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except Exception:
        return None


__all__ = ["parse_action"]
