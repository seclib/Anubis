"""Simple runtime memory persisted in ``state/runtime.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MEMORY_FILE = Path("state/runtime.json")


def _default_memory() -> dict[str, Any]:
    return {
        "tasks": [],
        "actions": [],
        "tool_results": [],
        "errors": [],
        "progression": {
            "status": "idle",
            "current_step": 0,
            "completed_steps": 0,
            "max_steps": 0,
            "percent": 0,
        },
        "task": None,
        "steps": [],
        "last_action": None,
        "last_result": None,
        "final_result": None,
    }


def _normalize_memory(memory: Any) -> dict[str, Any]:
    normalized = _default_memory()
    if isinstance(memory, dict):
        normalized.update(memory)

    for key in ("tasks", "actions", "tool_results", "errors", "steps"):
        if not isinstance(normalized.get(key), list):
            normalized[key] = []

    default_progression = _default_memory()["progression"]
    progression = normalized.get("progression")
    if not isinstance(progression, dict):
        normalized["progression"] = default_progression.copy()
    else:
        merged_progression = default_progression.copy()
        merged_progression.update(progression)
        normalized["progression"] = merged_progression

    return normalized


def _ensure_memory(memory: dict[str, Any]) -> None:
    normalized = _normalize_memory(memory)
    memory.clear()
    memory.update(normalized)


def _sync_current_task(memory: dict[str, Any]) -> None:
    task_text = memory.get("task")
    if not task_text:
        return

    created_at = memory.get("created_at")
    task_id = created_at or "current"
    task_entry = {
        "task_id": task_id,
        "task": task_text,
        "status": memory.get("status", memory["progression"].get("status", "running")),
        "created_at": created_at,
        "updated_at": memory.get("updated_at"),
        "completed_at": memory.get("completed_at"),
        "progression": memory.get("progression", {}).copy(),
        "final_result": memory.get("final_result"),
    }

    for index, existing in enumerate(memory["tasks"]):
        if isinstance(existing, dict) and existing.get("task_id") == task_id:
            memory["tasks"][index] = task_entry
            return

    memory["tasks"].append(task_entry)


def load_memory() -> dict[str, Any]:
    """Load memory from ``state/runtime.json``."""
    if not MEMORY_FILE.exists():
        return _default_memory()

    try:
        data = json.loads(MEMORY_FILE.read_text())
    except Exception:
        return _default_memory()

    return _normalize_memory(data)


def save_memory(memory: dict[str, Any]) -> None:
    """Save memory to ``state/runtime.json``."""
    _ensure_memory(memory)
    max_steps = memory.get("max_steps") or memory["progression"].get("max_steps", 0)
    completed_steps = len(memory.get("steps", []))
    current_step = memory["progression"].get(
        "current_step",
        memory.get("step_in_cycle", completed_steps),
    )
    percent = int(min(100, (current_step / max_steps) * 100)) if max_steps else 0
    memory["progression"].update(
        {
            "status": memory.get("status", memory["progression"].get("status", "idle")),
            "current_step": current_step,
            "completed_steps": completed_steps,
            "max_steps": max_steps,
            "percent": percent,
        }
    )
    _sync_current_task(memory)
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2, ensure_ascii=False, default=str))


def append_event(memory: dict[str, Any], event: dict[str, Any]) -> None:
    """Append an action/tool event and update derived memory fields."""
    _ensure_memory(memory)
    memory["steps"].append(event)

    action_entry = {
        "step": event.get("step"),
        "action": event.get("action"),
        "tool": event.get("tool"),
        "args": event.get("args", {}),
        "reason": event.get("reason", ""),
        "next_step": event.get("next_step", ""),
    }
    memory["actions"].append(action_entry)

    result = event.get("result", {})
    tool_result = {
        "step": event.get("step"),
        "tool": event.get("tool"),
        "success": result.get("success") if isinstance(result, dict) else None,
        "output": result.get("output") if isinstance(result, dict) else result,
    }
    memory["tool_results"].append(tool_result)

    if isinstance(result, dict) and result.get("success") is False:
        memory["errors"].append(
            {
                "step": event.get("step"),
                "tool": event.get("tool"),
                "error": result.get("output"),
            }
        )

    completed_steps = len(memory["steps"])
    max_steps = memory.get("max_steps") or memory["progression"].get("max_steps", 0)
    current_step = event.get(
        "cycle_step",
        memory["progression"].get("current_step", completed_steps),
    )
    percent = int(min(100, (current_step / max_steps) * 100)) if max_steps else 0
    memory["progression"].update(
        {
            "status": memory.get("status", "running"),
            "current_step": current_step,
            "completed_steps": completed_steps,
            "max_steps": max_steps,
            "percent": percent,
            "last_tool": event.get("tool"),
            "last_success": tool_result["success"],
        }
    )


def get_context_summary(memory: dict[str, Any]) -> str:
    """Build a short summary of the current task context."""
    normalized = _normalize_memory(memory)
    progression = normalized["progression"]
    current_task = normalized.get("task") or "None"

    lines = [
        f"Task: {current_task}",
        (
            "Progression: "
            f"cycle {progression.get('current_step', 0)}/{progression.get('max_steps', 0)} "
            f"({progression.get('percent', 0)}%), total={progression.get('completed_steps', 0)}"
        ),
        f"Status: {progression.get('status', 'idle')}",
    ]

    if normalized["steps"]:
        lines.append("Recent steps:")
        for event in normalized["steps"][-5:]:
            result = event.get("result", {})
            success = result.get("success") if isinstance(result, dict) else None
            output = result.get("output") if isinstance(result, dict) else result
            lines.append(
                f"- Step {event.get('step', '?')}: {event.get('tool', '?')} "
                f"success={success} output={str(output)[:120]}"
            )

    if normalized["errors"]:
        lines.append("Recent errors:")
        for error in normalized["errors"][-3:]:
            lines.append(
                f"- Step {error.get('step', '?')}: {error.get('tool', '?')} "
                f"-> {str(error.get('error'))[:120]}"
            )

    return "\n".join(lines)


def get_task_state_summary(memory: dict[str, Any]) -> str:
    """Build a human-readable summary for the CLI status command."""
    normalized = _normalize_memory(memory)
    progression = normalized["progression"]

    lines = [
        f"Current task: {normalized.get('task') or 'None'}",
        f"Tasks stored: {len(normalized['tasks'])}",
        f"Actions stored: {len(normalized['actions'])}",
        f"Tool results stored: {len(normalized['tool_results'])}",
        f"Errors stored: {len(normalized['errors'])}",
        (
            "Progression: "
            f"status={progression.get('status', 'idle')}, "
            f"step={progression.get('current_step', 0)}/{progression.get('max_steps', 0)}, "
            f"percent={progression.get('percent', 0)}%"
        ),
    ]

    if normalized["tasks"]:
        latest_task = normalized["tasks"][-1]
        lines.append(f"Latest task: {latest_task.get('task')}")
        lines.append(f"Latest task status: {latest_task.get('status')}")

    if normalized["errors"]:
        latest_error = normalized["errors"][-1]
        lines.append(
            "Last error: "
            f"{latest_error.get('tool', '?')} -> {str(latest_error.get('error'))[:160]}"
        )

    return "\n".join(lines)


__all__ = [
    "MEMORY_FILE",
    "append_event",
    "get_context_summary",
    "get_task_state_summary",
    "load_memory",
    "save_memory",
]
