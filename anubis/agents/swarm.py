from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Mapping

from anubis.agents.registry import AgentRegistry

AGENT_ORDER = ("builder", "researcher", "analyst")


@dataclass(frozen=True)
class SwarmAssignment:
    agent: str
    task: str


@dataclass(frozen=True)
class SwarmAgentResult:
    agent: str
    task: str
    output: str
    log: str


@dataclass(frozen=True)
class AgentExecutor:
    """Small deterministic executor used by the swarm dispatcher."""

    name: str
    action: str

    def execute(self, task: str) -> SwarmAgentResult:
        log = f"{self.name}: starting {task}"
        time.sleep(0.01)
        return SwarmAgentResult(
            agent=self.name,
            task=task,
            output=f"{self.name}: {self.action} {task}",
            log=log,
        )


class AgentDispatcher:
    """Routes planned tasks to registered agent executors."""

    def __init__(self, executors: Mapping[str, AgentExecutor] | None = None) -> None:
        self.executors = dict(executors or default_agent_executors())

    def register(self, executor: AgentExecutor) -> None:
        self.executors[executor.name] = executor

    def dispatch(self, assignment: SwarmAssignment) -> SwarmAgentResult:
        executor = self.executors.get(assignment.agent)
        if executor is None:
            executor = AgentExecutor(assignment.agent, "completed")
        return executor.execute(assignment.task)

    def execute_parallel(self, assignments: list[SwarmAssignment], event_bus: Any | None = None) -> list[SwarmAgentResult]:
        if not assignments:
            return []

        by_agent: dict[str, SwarmAgentResult] = {}
        with ThreadPoolExecutor(max_workers=len(assignments), thread_name_prefix="anubis-swarm") as executor:
            futures = {executor.submit(self._dispatch_with_events, assignment, event_bus): assignment for assignment in assignments}
            for future in as_completed(futures):
                result = future.result()
                by_agent[result.agent] = result

        return [by_agent[assignment.agent] for assignment in assignments]

    def _dispatch_with_events(self, assignment: SwarmAssignment, event_bus: Any | None) -> SwarmAgentResult:
        _emit(event_bus, "agent_started", {"agent": assignment.agent, "task": assignment.task, "progress": 0})
        _emit(event_bus, "agent_progress", {"agent": assignment.agent, "task": assignment.task, "progress": 40})
        result = self.dispatch(assignment)
        _emit(event_bus, "agent_progress", {"agent": assignment.agent, "task": assignment.task, "progress": 80})
        _emit(event_bus, "agent_completed", {"agent": assignment.agent, "task": assignment.task, "progress": 100, "output": result.output})
        return result


@dataclass(frozen=True)
class SwarmResult:
    goal: str
    assignments: list[SwarmAssignment]
    agent_results: list[SwarmAgentResult]
    logs: list[str]
    aggregate: str
    aggregation: dict[str, str]

    def render(self) -> str:
        lines = [
            f"goal: {self.goal}",
            "assignments:",
            *(f"- {item.agent} -> {item.task}" for item in self.assignments),
            "outputs:",
            *(f"- {item.output}" for item in self.agent_results),
            "aggregate: combined swarm result prepared",
            self.aggregate,
        ]
        return "\n".join(lines)

    def render_logs(self) -> str:
        return "\n".join(self.logs)

    def render_outputs(self) -> str:
        return render_swarm_output(self.aggregation, self.assignments)


class SwarmEngine:
    """Deterministic parallel swarm executor for ANUBIS agent state."""

    def __init__(self, agents: AgentRegistry, dispatcher: AgentDispatcher | None = None, event_bus: Any | None = None) -> None:
        self.agents = agents
        self.dispatcher = dispatcher or AgentDispatcher()
        self.event_bus = event_bus

    def run(self, goal: str) -> SwarmResult:
        clean_goal = " ".join(goal.split())
        _emit(self.event_bus, "swarm_started", {"goal": clean_goal})
        plan = self._planning_phase(clean_goal)
        assignments = self._assignment_phase(plan)
        logs = [
            f"planning: {clean_goal}",
            f"reasoning: {plan['reasoning']}",
            f"subtasks: {len(assignments)}",
        ]

        self._mark_running(assignments)
        agent_results = self._execution_phase(assignments)
        self._mark_completed(agent_results)
        aggregation = self._aggregation_phase(agent_results)
        _emit(self.event_bus, "swarm_completed", {"goal": clean_goal, "result": aggregation})
        for result in agent_results:
            logs.append(result.log)
        logs.append("aggregation: complete")

        return SwarmResult(
            goal=clean_goal,
            assignments=assignments,
            agent_results=agent_results,
            logs=logs,
            aggregate=render_aggregation(aggregation),
            aggregation=aggregation,
        )

    def plan(self, goal: str) -> list[SwarmAssignment]:
        plan = plan_swarm(goal)
        return self.assign(plan)

    def assign(self, plan: dict) -> list[SwarmAssignment]:
        assignments = _validate_plan(plan)
        return [SwarmAssignment(agent, assignments[agent]) for agent in AGENT_ORDER]

    def _planning_phase(self, goal: str) -> dict:
        return plan_swarm(goal)

    def _assignment_phase(self, plan: dict) -> list[SwarmAssignment]:
        return self.assign(plan)

    def _execution_phase(self, assignments: list[SwarmAssignment]) -> list[SwarmAgentResult]:
        return self.dispatcher.execute_parallel(assignments, self.event_bus)

    def _aggregation_phase(self, results: list[SwarmAgentResult]) -> dict:
        return aggregate_results(results)

    def _mark_running(self, assignments: list[SwarmAssignment]) -> None:
        for assignment in assignments:
            self.agents.update(assignment.agent, "running")
        self.agents.update("orchestrator", "active")

    def _mark_completed(self, results: list[SwarmAgentResult]) -> None:
        for result in results:
            self.agents.update(result.agent, "completed")
        self.agents.update("orchestrator", "active")


def plan_swarm(goal: str) -> dict:
    """Return a deterministic structured swarm plan for a high-level goal."""
    clean_goal = " ".join(goal.split())
    subject = _subject(clean_goal)
    kind = _goal_kind(clean_goal)

    if kind == "ui":
        assignments = {
            "builder": f"UI structure for {subject}",
            "researcher": f"design inspiration for {subject}",
            "analyst": f"optimization for {subject}",
        }
        reasoning = "Split UI work into structure, context, and optimization."
    elif kind == "backend":
        assignments = {
            "builder": f"build the service structure for {subject}",
            "researcher": f"gather API and integration context for {subject}",
            "analyst": f"review reliability, failure modes, and constraints for {subject}",
        }
        reasoning = "Split service work into implementation, integration research, and reliability review."
    elif kind == "debug":
        assignments = {
            "builder": f"prepare the patch path for {subject}",
            "researcher": f"gather failure context and reproduction clues for {subject}",
            "analyst": f"identify root cause and regression risks for {subject}",
        }
        reasoning = "Split debugging into patch planning, evidence gathering, and risk analysis."
    else:
        assignments = {
            "builder": f"define the execution path for {subject}",
            "researcher": f"discover context and requirements for {subject}",
            "analyst": f"review risks, constraints, and improvements for {subject}",
        }
        reasoning = "Split general work into execution, context discovery, and quality review."

    tasks = [
        assignments["researcher"],
        assignments["builder"],
        assignments["analyst"],
    ]

    return {
        "plan": tasks,
        "agent_assignment": assignments,
        "reasoning": reasoning,
    }


def _validate_plan(plan: dict) -> dict[str, str]:
    tasks = plan.get("plan")
    if not isinstance(tasks, list) or not 2 <= len(tasks) <= 5:
        raise ValueError("swarm plan must contain 2 to 5 tasks")

    assignments = plan.get("agent_assignment")
    if not isinstance(assignments, dict):
        raise ValueError("swarm plan must contain agent assignments")

    missing = [agent for agent in AGENT_ORDER if not str(assignments.get(agent, "")).strip()]
    if missing:
        raise ValueError(f"swarm plan missing assignments for: {', '.join(missing)}")

    return {agent: str(assignments[agent]).strip() for agent in AGENT_ORDER}


def render_swarm_plan(plan: dict) -> str:
    tasks = list(plan.get("plan", []))
    assignments = dict(plan.get("agent_assignment", {}))
    reasoning = str(plan.get("reasoning", "")).strip()
    lines = ["PLAN:"]
    lines.extend(f"- task {index}: {task}" for index, task in enumerate(tasks, start=1))
    lines.extend(["", "AGENT ASSIGNMENT:"])
    lines.extend(f"- {agent}: {assignments.get(agent, '')}" for agent in AGENT_ORDER)
    lines.extend(["", "REASONING (brief):", reasoning])
    return "\n".join(lines)


def aggregate_results(results: list) -> dict:
    """Synthesize agent outputs into a clean final swarm result."""
    contributions = {agent: "" for agent in AGENT_ORDER}
    for result in results:
        agent, output = _result_parts(result)
        if agent in contributions and output:
            contributions[agent] = _dedupe_sentence(output)

    available = [value for value in contributions.values() if value]
    unified = "; ".join(_unique(available)) if available else "No agent output produced."
    final_insight = _final_insight(contributions)

    return {
        "task": "Swarm aggregation",
        "result": unified,
        "builder_contribution": contributions["builder"] or "No builder contribution.",
        "researcher_contribution": contributions["researcher"] or "No researcher contribution.",
        "analyst_contribution": contributions["analyst"] or "No analyst contribution.",
        "final_insight": final_insight,
    }


def render_aggregation(aggregation: dict) -> str:
    return "\n".join(
        [
            "TASK:",
            str(aggregation.get("task", "Swarm aggregation")),
            "",
            "RESULT:",
            str(aggregation.get("result", "")),
            "",
            "BREAKDOWN:",
            f"- builder contribution: {aggregation.get('builder_contribution', '')}",
            f"- researcher contribution: {aggregation.get('researcher_contribution', '')}",
            f"- analyst contribution: {aggregation.get('analyst_contribution', '')}",
            "",
            "FINAL INSIGHT:",
            str(aggregation.get("final_insight", "")),
        ]
    )


def render_swarm_output(aggregation: dict, assignments: list[SwarmAssignment]) -> str:
    return "\n".join(
        [
            str(aggregation.get("result", "")),
            "",
            "BREAKDOWN:",
            f"- builder contribution: {aggregation.get('builder_contribution', '')}",
            f"- researcher contribution: {aggregation.get('researcher_contribution', '')}",
            f"- analyst contribution: {aggregation.get('analyst_contribution', '')}",
            "",
            "FINAL INSIGHT:",
            str(aggregation.get("final_insight", "")),
            "",
            "aggregate: combined swarm result prepared",
            "assignments:",
            *(f"- {item.agent} -> {item.task}" for item in assignments),
        ]
    )


def _goal_kind(goal: str) -> str:
    lowered = goal.lower()
    if any(word in lowered for word in ("landing", "page", "ui", "interface", "frontend")):
        return "ui"
    if any(word in lowered for word in ("api", "backend", "service", "server")):
        return "backend"
    if any(word in lowered for word in ("debug", "fix", "error", "failure", "bug")):
        return "debug"
    return "general"


def _subject(goal: str) -> str:
    words = [word.strip(" ,.;:") for word in goal.split() if word.strip(" ,.;:")]
    return " ".join(words[:5]) if words else "goal"


def _result_parts(result: Any) -> tuple[str, str]:
    if isinstance(result, SwarmAgentResult):
        return result.agent, result.output
    if isinstance(result, Mapping):
        return str(result.get("agent", "")).strip(), str(result.get("output", result.get("result", ""))).strip()
    text = str(result).strip()
    agent, separator, output = text.partition(":")
    if separator:
        return agent.strip().lower(), output.strip()
    return "", text


def _dedupe_sentence(text: str) -> str:
    return " ".join(text.split())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(value)
    return unique_values


def _final_insight(contributions: Mapping[str, str]) -> str:
    present = [agent for agent in AGENT_ORDER if contributions.get(agent)]
    if len(present) == 3:
        return "The swarm combined structure, context, and optimization into one execution-ready direction."
    if present:
        return f"The swarm produced a partial result from {', '.join(present)}."
    return "The swarm did not produce enough signal to form a final insight."


def default_agent_executors() -> dict[str, AgentExecutor]:
    return {
        "builder": AgentExecutor("builder", "builds structure for"),
        "researcher": AgentExecutor("researcher", "gathers insights for"),
        "analyst": AgentExecutor("analyst", "optimizes"),
    }


def _emit(event_bus: Any | None, event_type: str, payload: dict[str, Any]) -> None:
    if event_bus is not None:
        event_bus.emit(event_type, payload)


__all__ = [
    "AgentDispatcher",
    "AgentExecutor",
    "SwarmAgentResult",
    "SwarmAssignment",
    "SwarmEngine",
    "SwarmResult",
    "aggregate_results",
    "default_agent_executors",
    "plan_swarm",
    "render_aggregation",
    "render_swarm_output",
    "render_swarm_plan",
]
