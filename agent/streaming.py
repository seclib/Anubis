"""Helpers for rendering live agent progress events."""

from __future__ import annotations

import json
from typing import Any


def short_text(value: Any, limit: int = 300) -> str:
    """Return a compact, display-safe representation of an event value."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text[:limit]


def _result_summary(event: dict[str, Any], limit: int = 300) -> str:
    if event.get("result") is not None:
        return short_text(event["result"], limit)
    if event.get("verification") is not None:
        return short_text(event["verification"], limit)
    if event.get("final_result") is not None:
        return short_text(event["final_result"], limit)
    return ""


def progress_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    """Extract stable progress fields for live execution UIs."""
    snapshot: dict[str, Any] = {}
    for key in ("state", "cycle", "step", "total_steps", "max_steps", "status"):
        value = event.get(key)
        if value is not None:
            snapshot[key] = value

    progression = event.get("progression")
    if isinstance(progression, dict):
        snapshot.update(
            {
                key: value
                for key, value in progression.items()
                if key
                in {
                    "status",
                    "state",
                    "current_step",
                    "completed_steps",
                    "max_steps",
                    "percent",
                    "successful_tools",
                }
            }
        )

    return snapshot


def agent_event_payload(event: dict[str, Any], sequence: int | None = None) -> dict[str, Any]:
    """Build a structured event payload for native SSE consumers."""
    payload = dict(event)
    if sequence is not None:
        payload["sequence"] = sequence

    summary = _result_summary(event, limit=800)
    if summary:
        payload["result_summary"] = summary

    progress = progress_snapshot(event)
    if progress:
        payload["progress"] = progress

    return payload


def format_progress_event(event: dict[str, Any]) -> str:
    """Render a progress event as assistant-visible text."""
    event_type = str(event.get("type", "progress"))
    message = str(event.get("message", "")).strip()
    state = event.get("state")
    prefix = f"[{event_type.upper()}]"
    if state:
        prefix += f" [{state}]"

    details: list[str] = []
    if event_type in {
        "agent_start",
        "agent_message",
        "tool_start",
        "tool_result",
        "tool_error",
        "tool_correction",
        "tool_correction_error",
        "strategy_change",
    }:
        if event.get("agent"):
            details.append(f"agent={event['agent']}")
        if event.get("phase"):
            details.append(f"phase={event['phase']}")
        if event.get("tool"):
            details.append(f"tool={event['tool']}")
        if event.get("attempt"):
            details.append(f"attempt={event['attempt']}")

    if event_type in {"state", "plan", "action", "verification", "cycle_restart"}:
        if event.get("cycle"):
            details.append(f"cycle={event['cycle']}")
        if event.get("step") is not None:
            details.append(f"step={event['step']}")
        if event.get("total_steps") is not None:
            details.append(f"total={event['total_steps']}")

    if event_type == "repo_analysis" and event.get("architecture_summary"):
        details.append(str(event["architecture_summary"]))

    summary = _result_summary(event, limit=800 if event_type == "complete" else 300)
    if summary and event_type in {
        "intermediate_result",
        "verification",
        "tool_result",
        "tool_error",
        "complete",
        "blocked",
    }:
        details.append(summary)

    if event_type == "blocked" and event.get("reason"):
        details.append(str(event["reason"]))

    detail_text = f" ({', '.join(details)})" if details else ""
    return f"{prefix} {message}{detail_text}\n\n"


def format_sse_event(
    event_name: str,
    payload: dict[str, Any],
    *,
    event_id: int | None = None,
) -> str:
    """Serialize a Server-Sent Event with JSON data."""
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


__all__ = [
    "agent_event_payload",
    "format_progress_event",
    "format_sse_event",
    "progress_snapshot",
    "short_text",
]
