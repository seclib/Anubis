from __future__ import annotations

import os
from dataclasses import dataclass


PROMPT_TEXT = "anubis >"
COMPACT_PROMPT_TEXT = ">"
ALLOWED_PROMPTS = {PROMPT_TEXT, COMPACT_PROMPT_TEXT}


@dataclass(frozen=True)
class TerminalTheme:
    prompt: str = PROMPT_TEXT

    def render_prompt(self) -> str:
        return self.prompt

    def muted_text(self, text: object) -> str:
        return str(text)


DEFAULT_THEME = TerminalTheme()


def selected_prompt() -> str:
    value = os.environ.get("ANUBIS_CLI_PROMPT", PROMPT_TEXT).strip()
    return value if value in ALLOWED_PROMPTS else PROMPT_TEXT


__all__ = [
    "ALLOWED_PROMPTS",
    "COMPACT_PROMPT_TEXT",
    "DEFAULT_THEME",
    "PROMPT_TEXT",
    "TerminalTheme",
    "selected_prompt",
]
