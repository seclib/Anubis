"""Dedicated coding agent contract and prompt helpers."""

from __future__ import annotations

from typing import Any

CODER_AGENT = "coder_agent"

RECOMMENDED_CODER_MODEL = "qwen2.5-coder:7b"

CODER_RESPONSIBILITIES = [
    "modify_code",
    "create_files",
    "refactor_existing_code",
    "implement_features",
]

CODER_RULES = [
    "produce minimal clean code",
    "respect the existing architecture",
    "avoid unnecessary changes",
    "keep edits focused on the user task",
    "prefer existing project patterns over new abstractions",
]

CODER_PROMPT = """You are coder_agent, the implementation specialist of Anubis.

Responsibilities:
- Modify code.
- Create files.
- Refactor existing code.
- Implement features.

Coding rules:
- Produce minimal, clean code.
- Respect the existing architecture.
- Avoid unnecessary changes.
- Keep edits focused on the user task.
- Prefer existing project patterns over new abstractions.
- Do not perform unrelated refactors.
- Do not ask humans for help.

Use tools through the orchestrated JSON action protocol only."""


def create_coder_state() -> dict[str, Any]:
    return {
        "agent": CODER_AGENT,
        "recommended_model": RECOMMENDED_CODER_MODEL,
        "responsibilities": CODER_RESPONSIBILITIES,
        "rules": CODER_RULES,
        "status": "ready",
    }


def build_coder_context(memory: dict[str, Any]) -> str:
    coder_state = memory.get("coder_agent")
    if not isinstance(coder_state, dict):
        coder_state = create_coder_state()
        memory["coder_agent"] = coder_state

    return (
        "Coder agent contract:\n"
        + "\n".join(f"- {item}" for item in CODER_RESPONSIBILITIES)
        + "\n\nCoder rules:\n"
        + "\n".join(f"- {item}" for item in CODER_RULES)
        + f"\n\nRecommended model: {RECOMMENDED_CODER_MODEL}"
    )


__all__ = [
    "CODER_PROMPT",
    "CODER_RESPONSIBILITIES",
    "CODER_RULES",
    "RECOMMENDED_CODER_MODEL",
    "build_coder_context",
    "create_coder_state",
]
