from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def format_output(task: str, status: str | Mapping[str, Any] | None, result: str) -> str:
    return "\n".join(
        [
            "TASK:",
            _clean(task),
            "",
            "STATUS:",
            format_status(status),
            "",
            "RESULT:",
            _clean(result),
            "",
        ]
    )


def format_status(status: str | Mapping[str, Any] | None) -> str:
    if status is None:
        return "ready"
    if isinstance(status, str):
        return _clean(status)
    if "__logs__" in status:
        return _clean(status["__logs__"])
    if not status:
        return "ready"
    return "\n".join(f"- {key}: {status[key]}" for key in sorted(status))


def write_output(text: str) -> None:
    print(text, end="" if text.endswith("\n") else "\n")


def _clean(value: object) -> str:
    text = str(value).strip()
    return text or "none"


__all__ = ["format_output", "format_status", "write_output"]
