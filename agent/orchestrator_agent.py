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
    "decompose_complex_tasks",
    "prioritize_critical_steps",
    "manage_step_dependencies",
    "parallelize_agents_when_possible",
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

TOOL_PHASE_MAP = {
    "read_file": "analysis",
    "list_files": "analysis",
    "scan_repo_tree": "analysis",
    "detect_project_type": "analysis",
    "find_entrypoints": "analysis",
    "find_file": "analysis",
    "get_file_tree": "analysis",
    "search_code": "analysis",
    "write_file": "action",
    "create_dynamic_tool": "action",
    "run_command": "test_verification",
    "run_git_validations": "test_verification",
    "autonomous_git_commit": "test_verification",
    "rollback_last_autonomous_commit": "debug",
}

CRITICAL_KEYWORDS = {
    "security": 30,
    "sandbox": 30,
    "test": 25,
    "validate": 25,
    "fix": 25,
    "bug": 25,
    "error": 25,
    "implement": 20,
    "create": 15,
    "doc": 5,
    "readme": 5,
}


def create_orchestrator_state(task: str) -> dict[str, Any]:
    return {
        "agent": ORCHESTRATOR_AGENT,
        "role": "Main brain of the autonomous multi-agent system",
        "task": task,
        "responsibilities": ORCHESTRATOR_RESPONSIBILITIES,
        "phase_agent_map": PHASE_AGENT_MAP,
        "priorities": PHASE_PRIORITIES,
        "priority_plan": [],
        "parallel_batches": [],
        "dependency_graph": {},
        "assignments": [],
        "results": [],
        "retry_counts": {},
        "status": "running",
    }


def select_agent_for_phase(phase: str) -> str:
    return PHASE_AGENT_MAP.get(phase, ORCHESTRATOR_AGENT)


def priority_for_phase(phase: str) -> int:
    return PHASE_PRIORITIES.get(phase, 50)


def _step_id(index: int, step: dict[str, Any]) -> str:
    raw_id = step.get("id") or step.get("step") or index
    return f"step_{raw_id}"


def _phase_for_step(step: dict[str, Any]) -> str:
    phase = str(step.get("phase") or "").strip()
    if phase:
        return phase
    tool_hint = str(step.get("tool_hint") or step.get("tool") or "").strip()
    return TOOL_PHASE_MAP.get(tool_hint, "action")


def _dependencies_for_step(index: int, step: dict[str, Any], phase: str, prior_ids: list[str]) -> list[str]:
    explicit = step.get("depends_on", step.get("dependencies", []))
    if isinstance(explicit, str):
        dependencies = [explicit]
    elif isinstance(explicit, list):
        dependencies = [str(item) for item in explicit if str(item).strip()]
    else:
        dependencies = []

    if dependencies:
        return dependencies

    if index == 0:
        return []

    if phase in {"action", "debug"}:
        return prior_ids[-1:]
    if phase in {"review", "test_verification"}:
        action_ids = [step_id for step_id in prior_ids if "action" in step_id or "debug" in step_id]
        return action_ids[-1:] or prior_ids[-1:]
    if phase == "memory_summary":
        return prior_ids[-2:]
    return []


def _priority_for_step(step: dict[str, Any], phase: str) -> int:
    priority = priority_for_phase(phase)
    text = f"{step.get('goal', '')} {step.get('description', '')} {step.get('tool_hint', '')}".lower()
    for keyword, boost in CRITICAL_KEYWORDS.items():
        if keyword in text:
            priority += boost
    if step.get("critical") is True:
        priority += 40
    return min(priority, 200)


def build_priority_plan(task: str, plan: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a dependency-aware, priority-sorted orchestration plan."""
    normalized_steps: list[dict[str, Any]] = []
    prior_ids: list[str] = []

    for index, raw_step in enumerate(plan):
        step = raw_step if isinstance(raw_step, dict) else {"goal": str(raw_step)}
        phase = _phase_for_step(step)
        step_id = _step_id(index + 1, step)
        dependencies = _dependencies_for_step(index, step, phase, prior_ids)
        priority = _priority_for_step(step, phase)
        normalized = {
            **step,
            "id": step_id,
            "phase": phase,
            "agent": select_agent_for_phase(phase),
            "priority": priority,
            "depends_on": dependencies,
            "parallelizable": phase in {"analysis", "review", "test_verification", "memory_summary"},
            "status": "pending",
        }
        normalized_steps.append(normalized)
        prior_ids.append(step_id)

    dependency_graph = {step["id"]: list(step["depends_on"]) for step in normalized_steps}
    parallel_batches = build_parallel_batches(normalized_steps)
    critical_path = [
        step["id"]
        for step in sorted(normalized_steps, key=lambda item: item["priority"], reverse=True)
        if step["priority"] >= 100
    ]

    return {
        "task": task,
        "steps": sorted(normalized_steps, key=lambda item: (-item["priority"], len(item["depends_on"]), item["id"])),
        "dependency_graph": dependency_graph,
        "parallel_batches": parallel_batches,
        "critical_path": critical_path,
    }


def build_parallel_batches(steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group ready steps into priority-ordered batches that can run in parallel."""
    pending = {step["id"]: dict(step) for step in steps}
    completed: set[str] = set()
    batches: list[list[dict[str, Any]]] = []

    while pending:
        ready = [
            step
            for step in pending.values()
            if all(dependency in completed for dependency in step.get("depends_on", []))
        ]
        if not ready:
            ready = [max(pending.values(), key=lambda item: item.get("priority", 0))]

        ready.sort(key=lambda item: item.get("priority", 0), reverse=True)
        parallel_batch = ready if all(step.get("parallelizable") for step in ready) else ready[:1]
        batches.append(parallel_batch)

        for step in parallel_batch:
            pending.pop(step["id"], None)
            completed.add(step["id"])

    return batches


def update_priority_engine(memory: dict[str, Any], task: str, plan: list[dict[str, Any]]) -> dict[str, Any]:
    orchestration = ensure_orchestrator_state(memory)
    priority_plan = build_priority_plan(task, plan)
    orchestration["priority_plan"] = priority_plan["steps"]
    orchestration["parallel_batches"] = priority_plan["parallel_batches"]
    orchestration["dependency_graph"] = priority_plan["dependency_graph"]
    orchestration["critical_path"] = priority_plan["critical_path"]
    memory["priority_plan"] = priority_plan
    return priority_plan


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
                "critical_path": orchestration.get("critical_path", []),
                "dependency_graph": orchestration.get("dependency_graph", {}),
                "parallel_batches": orchestration.get("parallel_batches", []),
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
    "build_parallel_batches",
    "build_orchestrator_context",
    "build_priority_plan",
    "create_orchestrator_state",
    "ensure_orchestrator_state",
    "priority_for_phase",
    "record_assignment",
    "record_result",
    "record_retry",
    "select_agent_for_phase",
    "update_priority_engine",
]
