"""Runtime-facing prompt helpers for non-agent layers."""

from __future__ import annotations

from config import PROJECT_ROOT

DEFAULT_RUNTIME_SYSTEM_PROMPT = """You are Anubis, an autonomous CLI coding agent.
Be concise, technical, and action-oriented. Use tools through the runtime when
execution is required, and keep normal chat responses in Markdown."""


def build_cli_system_prompt(
    system_prompt: str = DEFAULT_RUNTIME_SYSTEM_PROMPT,
    *,
    project_root: str = str(PROJECT_ROOT),
) -> str:
    return f"""{system_prompt}

ADDITIONAL CLI RULES:
- You are in interactive terminal mode. Be concise and technical.
- When the user asks a direct question, answer it with Markdown.
- For tool execution, output the standard JSON action block.
- Current working directory: {project_root}
- Current date: {{date}}
""".strip()


CLI_SYSTEM_PROMPT = build_cli_system_prompt()
SYSTEM_PROMPT = DEFAULT_RUNTIME_SYSTEM_PROMPT

__all__ = ["CLI_SYSTEM_PROMPT", "DEFAULT_RUNTIME_SYSTEM_PROMPT", "SYSTEM_PROMPT", "build_cli_system_prompt"]
