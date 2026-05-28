"""Continuous self-improvement heuristics for Anubis."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _tool_results(memory: dict[str, Any]) -> list[dict[str, Any]]:
    values = memory.get("tool_results", [])
    return [value for value in values if isinstance(value, dict)]


def _errors(memory: dict[str, Any]) -> list[dict[str, Any]]:
    values = memory.get("errors", [])
    return [value for value in values if isinstance(value, dict)]


def _failure_key(error: dict[str, Any]) -> str:
    tool = str(error.get("tool") or "unknown_tool")
    payload = error.get("error")
    if isinstance(payload, dict):
        error_type = payload.get("type") or payload.get("error") or payload
    else:
        error_type = payload
    return f"{tool}:{str(error_type)[:120]}"


def analyze_performance(memory: dict[str, Any]) -> dict[str, Any]:
    """Analyze recent agent performance and recurring failure patterns."""
    tool_results = _tool_results(memory)
    errors = _errors(memory)
    total_tools = len(tool_results)
    successes = sum(1 for result in tool_results if result.get("success") is True)
    failures = sum(1 for result in tool_results if result.get("success") is False)
    success_rate = round(successes / total_tools, 3) if total_tools else 1.0

    tool_usage = Counter(str(result.get("tool") or "unknown_tool") for result in tool_results)
    failed_tools = Counter(str(result.get("tool") or "unknown_tool") for result in tool_results if result.get("success") is False)
    recurring_failures = [
        {
            "pattern": pattern,
            "count": count,
        }
        for pattern, count in Counter(_failure_key(error) for error in errors).most_common(8)
        if count >= 2
    ]

    return {
        "total_tool_calls": total_tools,
        "successful_tool_calls": successes,
        "failed_tool_calls": failures,
        "success_rate": success_rate,
        "most_used_tools": dict(tool_usage.most_common(8)),
        "most_failed_tools": dict(failed_tools.most_common(8)),
        "recurring_failures": recurring_failures,
        "cycles_without_progress": int(memory.get("cycles_without_progress", 0) or 0),
        "consecutive_failures": int(memory.get("consecutive_failures", 0) or 0),
    }


def propose_strategy_improvements(memory: dict[str, Any]) -> list[str]:
    """Produce compact strategy hints from observed performance."""
    analysis = analyze_performance(memory)
    suggestions: list[str] = []

    if analysis["success_rate"] < 0.6 and analysis["total_tool_calls"] >= 3:
        suggestions.append("Prefer read-only repo inspection before mutating files.")
        suggestions.append("Use smaller tool calls with explicit paths and validate each result.")

    if analysis["recurring_failures"]:
        suggestions.append("Do not repeat arguments from recurring failure patterns; switch tool or inspect context first.")

    failed_tools = analysis["most_failed_tools"]
    if failed_tools.get("read_file", 0) >= 2:
        suggestions.append("Before read_file, use find_file or scan_repo_tree to confirm the path.")
    if failed_tools.get("run_command", 0) >= 2:
        suggestions.append("Before run_command, inspect project entrypoints and prefer the narrowest validation command.")
    if failed_tools.get("write_file", 0) >= 2:
        suggestions.append("Before write_file, read the target file and preserve existing architecture/style.")

    if analysis["cycles_without_progress"] > 0:
        suggestions.append("Change strategy after a no-progress cycle; avoid replaying the same tool sequence.")

    if not suggestions:
        suggestions.append("Current strategy is healthy; continue with minimal, validated steps.")

    return suggestions[:6]


def optimize_prompt_guidance(memory: dict[str, Any]) -> str:
    """Build prompt-ready continuous improvement guidance."""
    analysis = analyze_performance(memory)
    suggestions = propose_strategy_improvements(memory)
    lines = [
        "Continuous improvement guidance:",
        f"- Tool success rate: {analysis['success_rate']} ({analysis['successful_tool_calls']}/{analysis['total_tool_calls']})",
        f"- Most failed tools: {analysis['most_failed_tools'] or {}}",
        f"- Recurring failures: {analysis['recurring_failures'] or []}",
        "- Strategy updates:",
    ]
    lines.extend(f"  - {suggestion}" for suggestion in suggestions)
    return "\n".join(lines)


def update_self_improvement_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Refresh self-improvement state in runtime memory."""
    state = {
        "performance": analyze_performance(memory),
        "strategy_improvements": propose_strategy_improvements(memory),
        "prompt_guidance": optimize_prompt_guidance(memory),
    }
    memory["self_improvement"] = state
    return state


__all__ = [
    "analyze_performance",
    "optimize_prompt_guidance",
    "propose_strategy_improvements",
    "update_self_improvement_memory",
]
