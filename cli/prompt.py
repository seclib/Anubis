from __future__ import annotations

from anubis.cli.theme import DEFAULT_THEME, PROMPT_TEXT, TerminalTheme, selected_prompt

PROMPT = PROMPT_TEXT


def render_prompt(theme: TerminalTheme | None = None) -> str:
    if theme is not None:
        return theme.render_prompt()
    configured = selected_prompt()
    if configured == DEFAULT_THEME.prompt:
        return DEFAULT_THEME.render_prompt()
    return configured


__all__ = ["PROMPT", "render_prompt"]
