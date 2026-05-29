"""Runtime-facing streaming facade.

CLI/API code depends on this module, not on ``agent``. The concrete formatter is
resolved only when a stream event is formatted, keeping module imports acyclic.
"""

from __future__ import annotations

from typing import Any


def _formatter(name: str):
    module = __import__("agent.streaming", fromlist=[name])
    return getattr(module, name)


def short_text(value: Any, limit: int = 300) -> str:
    return _formatter("short_text")(value, limit)


def agent_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return _formatter("agent_event_payload")(event)


def format_live_execution_event(event: dict[str, Any]) -> str:
    return _formatter("format_live_execution_event")(event)


def format_progress_event(event: dict[str, Any]) -> str:
    return _formatter("format_progress_event")(event)


def format_sse_event(event: dict[str, Any]) -> str:
    return _formatter("format_sse_event")(event)


__all__ = [
    "agent_event_payload",
    "format_live_execution_event",
    "format_progress_event",
    "format_sse_event",
    "short_text",
]
