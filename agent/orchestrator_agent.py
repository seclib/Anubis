"""Dedicated orchestration state and coordination helpers."""

from __future__ import annotations

from typing import Any

from agent.multi_agent import (
    CODER_AGENT,
    DEBUGGER_AGENT,
    MEMORY_AGENT,
    ORCHESTRATOR_AGENT,
    PLANNER_AGENT,
    REVIEWER_AGENT,
    TESTER_AGENT,
)
from agent.communication import send_agent_task


ORCHESTRATOR_RESPONSIBILITIES = [
    "receive_user_task",
    "distribute_work_to_specialized_agents",
    "coordinate_execution_steps",
    "aggregate_agent_results",
    "manage_retries_and_priorities",
]

PHASE_AGENT_MAP = {
    "analysis": ORCHESTRATOR_AGENT,
    "planning": PLANNER_AGENT,
    "action": CODER_AGENT,
    "review": REVIEWER_AGENT,
    "test_verification": TESTER_AGENT,
    "debug": DEBUGGER_AGENT,
    "memory_summary": MEMORY_AGENT,
}

PHASE_PRIORITIES = {
    "analysis": 100,
    "debug": 95,
    "action": 90,
    "planning": 80,
    "review": 70,
    "test_verification": 70,
    "memory_summary": 30,
}


def create_orchestrator_state(task: str) -> dict[str, Any]:
    return {
        "agent": ORCHESTRATOR_AGENT,
        "role": "Main brain of the autonomous multi-agent system",
        "task": task,
        "responsibilities": ORCHESTRATOR_RESPONSIBILITIES,
        "phase_agent_map": PHASE_AGENT_MAP,
        "priorities": PHASE_PRIORITIES,
        "assignments": [],
        "results": [],
        "retry_counts": {},
        "status": "running",
    }


def select_agent_for_phase(phase: str) -> str:
    return PHASE_AGENT_MAP.get(phase, ORCHESTRATOR_AGENT)


def priority_for_phase(phase: str) -> int:
    return PHASE_PRIORITIES.get(phase, 50)


def ensure_orchestrator_state(memory: dict[str, Any]) -> dict[str, Any]:
    orchestration = memory.get("orchestration")
    if not isinstance(orchestration, dict):
        orchestration = create_orchestrator_state(str(memory.get("task") or ""))
        memory["orchestration"] = orchestration
    return orchestration


def record_assignment(
    memory: dict[str, Any],
    *,
    target_agent: str,
    phase: str,
    reason: str,
) -> dict[str, Any]:
    orchestration = ensure_orchestrator_state(memory)
    assignment = {
        "from": ORCHESTRATOR_AGENT,
        "to": target_agent,
        "phase": phase,
        "priority": priority_for_phase(phase),
        "reason": reason,
    }
    orchestration.setdefault("assignments", []).append(assignment)
    orchestration["current_assignment"] = assignment
    task_message = send_agent_task(
        memory,
        sender=ORCHESTRATOR_AGENT,
        recipient=target_agent,
        task=reason,
        phase=phase,
        priority=priority_for_phase(phase),
        context={
            "assignment": assignment,
            "user_task": memory.get("task"),
        },
    )
    assignment["message_id"] = task_message["id"]
    return assignment


def record_result(
    memory: dict[str, Any],
    *,
    agent_name: str,
    phase: str,
    result: Any,
    success: bool = True,
) -> dict[str, Any]:
    orchestration = ensure_orchestrator_state(memory)
    entry = {
        "agent": agent_name,
        "phase": phase,
        "success": success,
        "result": result,
    }
    orchestration.setdefault("results", []).append(entry)
    orchestration["last_result"] = entry
    return entry


def record_retry(memory: dict[str, Any], *, phase: str, reason: str) -> int:
    orchestration = ensure_orchestrator_state(memory)
    retry_counts = orchestration.setdefault("retry_counts", {})
    retry_counts[phase] = int(retry_counts.get(phase, 0)) + 1
    orchestration["last_retry"] = {
        "phase": phase,
        "count": retry_counts[phase],
        "reason": reason,
    }
    return retry_counts[phase]


def aggregate_results(memory: dict[str, Any], limit: int = 8) -> str:
    orchestration = ensure_orchestrator_state(memory)
    results = orchestration.get("results", [])
    if not isinstance(results, list) or not results:
        return "No agent results aggregated yet."

    lines: list[str] = []
    for result in results[-limit:]:
        if not isinstance(result, dict):
            continue
        agent_name = result.get("agent", "unknown_agent")
        phase = result.get("phase", "unknown")
        success = result.get("success")
        text = str(result.get("result", ""))[:500]
        lines.append(f"- {agent_name} [{phase}] success={success}: {text}")

    return "\n".join(lines) if lines else "No agent results aggregated yet."


def build_orchestrator_context(memory: dict[str, Any]) -> str:
    orchestration = ensure_orchestrator_state(memory)
    return (
        "Orchestrator responsibilities:\n"
        + "\n".join(f"- {item}" for item in ORCHESTRATOR_RESPONSIBILITIES)
        + "\n\nCurrent orchestration state:\n"
        + str(
            {
                "status": orchestration.get("status"),
                "current_assignment": orchestration.get("current_assignment"),
                "last_retry": orchestration.get("last_retry"),
                "priorities": orchestration.get("priorities"),
            }
        )
        + "\n\nAggregated agent results:\n"
        + aggregate_results(memory)
    )


__all__ = [
    "ORCHESTRATOR_RESPONSIBILITIES",
    "PHASE_AGENT_MAP",
    "PHASE_PRIORITIES",
    "aggregate_results",
    "build_orchestrator_context",
    "create_orchestrator_state",
    "ensure_orchestrator_state",
    "priority_for_phase",
    "record_assignment",
    "record_result",
    "record_retry",
    "select_agent_for_phase",
]
