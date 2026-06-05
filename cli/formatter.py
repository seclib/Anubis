from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from anubis.agents import STATE_ORDER


def format_output(task: object, status: str | Mapping[str, Any] | None, result: object) -> str:
    return "\n".join(
        [
            "TASK:",
            clean(task),
            "",
            "STATUS:",
            format_status(status),
            "",
            "RESULT:",
            clean(result),
            "",
        ]
    )


def format_error(task: object, error: object, status: str = "error") -> str:
    return format_output(task, status, error)


def format_pipeline(outputs: list[str]) -> str:
    return "\n".join(output.rstrip() for output in outputs if output.strip()) + ("\n" if outputs else "")


def format_status(status: str | Mapping[str, Any] | None) -> str:
    if status is None:
        return "ready"
    if isinstance(status, str):
        return clean(status)
    if not status:
        return "ready"
    if "__logs__" in status:
        return clean(status["__logs__"])

    emitted: set[str] = set()
    lines: list[str] = []
    for name in STATE_ORDER:
        if name in status:
            lines.append(f"{name}: {status[name]}")
            emitted.add(name)
    for name in sorted(set(status) - emitted):
        lines.append(f"{name}: {status[name]}")
    return "\n".join(lines)


def render_block(task: object, status: str | Mapping[str, Any] | None, result: object) -> str:
    return format_output(task, status, result)


def write_output(text: str) -> None:
    print(text, end="" if text.endswith("\n") else "\n")


def clean(value: object) -> str:
    text = str(value).strip()
    return text or "none"


__all__ = [
    "clean",
    "format_error",
    "format_output",
    "format_pipeline",
    "format_status",
    "render_block",
    "write_output",
]
