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


def _tool_output(event: dict[str, Any]) -> Any:
    result = event.get("result")
    if isinstance(result, dict):
        return result.get("output")
    return None


def _shell_logs(event: dict[str, Any], limit: int = 3000) -> dict[str, Any]:
    output = _tool_output(event)
    if not isinstance(output, dict):
        return {}

    logs: dict[str, Any] = {}
    for key in ("stdout", "stderr"):
        value = output.get(key)
        if isinstance(value, str) and value:
            logs[key] = short_text(value, limit)

    for key in ("code", "timeout", "truncated"):
        if key in output:
            logs[key] = output[key]

    return logs


def _plan_steps(event: dict[str, Any]) -> list[Any]:
    plan = event.get("plan")
    if isinstance(plan, list):
        return plan
    return []


def live_execution_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    """Extract Open WebUI-friendly live execution fields."""
    event_type = str(event.get("type", "progress"))
    live: dict[str, Any] = {
        "type": event_type,
        "message": str(event.get("message", "")),
    }

    for source_key, target_key in (
        ("agent", "active_agent"),
        ("target_agent", "target_agent"),
        ("phase", "phase"),
        ("tool", "tool"),
        ("attempt", "attempt"),
        ("max_attempts", "max_attempts"),
        ("state", "state"),
        ("cycle", "cycle"),
        ("step", "step"),
    ):
        value = event.get(source_key)
        if value is not None:
            live[target_key] = value

    progress = progress_snapshot(event)
    if progress:
        live["progress"] = progress

    if event.get("args") is not None:
        live["tool_args"] = event["args"]
    if event.get("messages") is not None:
        live["messages"] = event["messages"]

    logs = _shell_logs(event)
    if logs:
        live["shell"] = logs

    plan = _plan_steps(event)
    if plan:
        live["plan"] = plan

    if event_type == "tool_correction":
        live["correction"] = {
            "analysis": event.get("analysis"),
            "retry": event.get("retry"),
            "corrected_args": event.get("corrected_args"),
            "reason": event.get("reason"),
        }

    if event.get("verification") is not None:
        live["verification"] = event["verification"]
    if event.get("result") is not None:
        live["result_summary"] = _result_summary(event, limit=1200)

    return live


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

    payload["live"] = live_execution_snapshot(event)

    return payload


def _markdown_code_block(value: str, language: str = "") -> str:
    if not value:
        return ""
    fence_language = language.strip()
    return f"```{fence_language}\n{value.rstrip()}\n```\n"


def _format_plan(plan: list[Any]) -> str:
    lines: list[str] = []
    for index, item in enumerate(plan, start=1):
        if isinstance(item, dict):
            goal = item.get("goal") or item.get("step") or item
            tool_hint = item.get("tool_hint")
            suffix = f" — tool: `{tool_hint}`" if tool_hint else ""
            lines.append(f"{index}. {goal}{suffix}")
        else:
            lines.append(f"{index}. {item}")
    return "\n".join(lines)


def format_live_execution_event(event: dict[str, Any]) -> str:
    """Render a progress event as Open WebUI-friendly live execution Markdown."""
    live = live_execution_snapshot(event)
    event_type = live["type"]
    message = live.get("message") or event_type

    icon_by_type = {
        "agent_start": "🧠",
        "agent_messages_delivered": "📨",
        "orchestrator_assignment": "🎯",
        "plan": "🗺️",
        "action": "⚙️",
        "tool_start": "🔧",
        "tool_result": "✅",
        "tool_error": "❌",
        "tool_correction": "🛠️",
        "tool_correction_error": "⚠️",
        "verification": "🔎",
        "intermediate_result": "📌",
        "complete": "🏁",
        "blocked": "⛔",
        "state": "📍",
    }
    icon = icon_by_type.get(event_type, "•")

    header_bits = [f"{icon} **{message}**"]
    if live.get("active_agent"):
        header_bits.append(f"agent: `{live['active_agent']}`")
    if live.get("phase"):
        header_bits.append(f"phase: `{live['phase']}`")
    if live.get("state"):
        header_bits.append(f"state: `{live['state']}`")
    text = " — ".join(header_bits) + "\n"

    if live.get("target_agent"):
        text += f"- Delegated to: `{live['target_agent']}`\n"
    if live.get("messages"):
        text += "- Inter-agent messages:\n" + _markdown_code_block(
            json.dumps(live["messages"], ensure_ascii=False, indent=2, default=str),
            "json",
        )
    if live.get("tool"):
        attempt = ""
        if live.get("attempt"):
            max_attempts = live.get("max_attempts")
            attempt = f" ({live['attempt']}/{max_attempts})" if max_attempts else f" ({live['attempt']})"
        text += f"- Tool: `{live['tool']}`{attempt}\n"
    if live.get("tool_args") is not None and event_type in {"tool_start", "tool_error", "tool_correction"}:
        text += "- Args:\n" + _markdown_code_block(
            json.dumps(live["tool_args"], ensure_ascii=False, indent=2, default=str),
            "json",
        )

    if live.get("plan"):
        text += "\n**Planning Steps**\n" + _format_plan(live["plan"]) + "\n"

    shell = live.get("shell")
    if isinstance(shell, dict) and shell:
        status = []
        if "code" in shell:
            status.append(f"exit `{shell['code']}`")
        if shell.get("timeout"):
            status.append("timeout")
        if shell.get("truncated"):
            status.append("truncated")
        suffix = f" ({', '.join(status)})" if status else ""
        text += f"\n**Shell Logs**{suffix}\n"
        if shell.get("stdout"):
            text += "stdout:\n" + _markdown_code_block(str(shell["stdout"]), "text")
        if shell.get("stderr"):
            text += "stderr:\n" + _markdown_code_block(str(shell["stderr"]), "text")

    correction = live.get("correction")
    if isinstance(correction, dict):
        text += "\n**Automatic Correction**\n"
        if correction.get("analysis"):
            text += f"- Analysis: {correction['analysis']}\n"
        if correction.get("reason"):
            text += f"- Reason: {correction['reason']}\n"
        if correction.get("corrected_args") is not None:
            text += "- Corrected args:\n" + _markdown_code_block(
                json.dumps(correction["corrected_args"], ensure_ascii=False, indent=2, default=str),
                "json",
            )

    if live.get("verification") is not None:
        text += "\n**Verification**\n" + _markdown_code_block(
            json.dumps(live["verification"], ensure_ascii=False, indent=2, default=str),
            "json",
        )

    if event_type in {"tool_result", "tool_error", "intermediate_result", "complete", "blocked"}:
        summary = live.get("result_summary")
        if summary:
            text += f"\n**Result**\n{summary}\n"

    return text.rstrip() + "\n\n"


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
    "format_live_execution_event",
    "format_progress_event",
    "format_sse_event",
    "live_execution_snapshot",
    "progress_snapshot",
    "short_text",
]
