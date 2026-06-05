"""Concrete ANUBIS nodes for graph-based orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.agents import AgentRegistry, build_default_agent_registry
from core.execution import SandboxRunRequest, SandboxRunner
from core.graph.node import GraphNode, NodeResult
from core.graph.state import GraphRunStatus, GraphState
from core.memory import MemoryManager
from core.planner import PlanningEngine, build_planning_engine


def _task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "kind": task.kind,
        "objective": task.objective,
        "required_capabilities": sorted(task.required_capabilities),
        "depends_on": sorted(task.depends_on),
        "priority": task.priority,
        "reason": task.reason,
        "metadata": dict(task.metadata),
    }


class InputNode(GraphNode):
    name = "input"

    def run(self, state: GraphState) -> NodeResult:
        if not state.stimulus:
            raise ValueError("stimulus cannot be empty")
        intent = {
            "kind": str(state.context.get("intent_kind") or "investigate_alert"),
            "objective": state.stimulus,
            "source": state.source,
            "explanation": "Input node normalized stimulus into a deterministic intent envelope.",
        }
        return NodeResult(
            state=state.with_updates(intent=intent),
            explanation="Accepted and normalized operator stimulus.",
            outputs={"intent": intent},
        )


@dataclass(slots=True)
class PlannerNode(GraphNode):
    planner: PlanningEngine = field(default_factory=build_planning_engine)
    name: str = "planner"

    def run(self, state: GraphState) -> NodeResult:
        intent_kind = str(state.intent.get("kind") or "investigate_alert")
        plan = self.planner.plan(state.stimulus, intent_kind=intent_kind)
        plan_payload = {
            "graph_id": plan.graph.graph_id,
            "intent": {
                "kind": plan.graph.intent.kind,
                "objective": plan.graph.intent.objective,
                "metadata": dict(plan.graph.intent.metadata),
            },
            "ordered_task_ids": list(plan.task_ids),
            "tasks": [_task_to_dict(task) for task in plan.ordered_tasks],
            "explanation": list(plan.explanation),
        }
        return NodeResult(
            state=state.with_updates(plan=plan_payload),
            explanation="Planner produced a deterministic ordered task graph.",
            outputs={"plan": plan_payload},
        )


@dataclass(slots=True)
class AgentDispatchNode(GraphNode):
    registry: AgentRegistry = field(default_factory=build_default_agent_registry)
    name: str = "agent_dispatch"

    def run(self, state: GraphState) -> NodeResult:
        tasks = state.plan.get("tasks", ())
        if not isinstance(tasks, (list, tuple)) or not tasks:
            raise ValueError("planner node must provide ordered tasks")

        assignments: list[dict[str, Any]] = []
        agent_results: list[dict[str, Any]] = []
        for task in tasks:
            task_payload = dict(task)
            role = self._role_for_task(str(task_payload.get("kind") or ""))
            agent = self.registry.select(role=role)
            agent_input = self._agent_input(role, state, task_payload, agent_results)
            result = agent.run(agent_input)
            assignments.append(
                {
                    "task_id": task_payload["task_id"],
                    "task_kind": task_payload["kind"],
                    "agent": agent.name,
                    "role": role,
                    "reason": self._assignment_reason(role, task_payload),
                }
            )
            agent_results.append(
                {
                    "task_id": task_payload["task_id"],
                    "agent": agent.name,
                    "role": role,
                    "result": result,
                }
            )

        return NodeResult(
            state=state.with_updates(
                assignments=tuple(assignments),
                agent_results=tuple(agent_results),
            ),
            explanation="Agent dispatch selected stateless workers by task kind.",
            outputs={"assignments": assignments, "agent_results": agent_results},
        )

    @staticmethod
    def _role_for_task(kind: str) -> str:
        if kind.startswith("planning."):
            return "planner"
        if kind.startswith("analysis.") or kind.startswith("memory."):
            return "analyst"
        if kind.startswith("policy."):
            return "critic"
        return "analyst"

    @staticmethod
    def _assignment_reason(role: str, task: Mapping[str, Any]) -> str:
        return f"Task kind '{task.get('kind')}' maps deterministically to role '{role}'."

    @staticmethod
    def _agent_input(
        role: str,
        state: GraphState,
        task: Mapping[str, Any],
        prior_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if role == "planner":
            return {"objective": task["objective"], "intent_kind": state.intent.get("kind")}
        if role == "critic":
            subject = prior_results[-1]["result"] if prior_results else {"ok": True, "output": task}
            return {"subject": subject}
        observations = list(state.context.get("observations") or ())
        observations.append({"id": task["task_id"], "summary": task["objective"]})
        return {"objective": task["objective"], "observations": observations}


@dataclass(slots=True)
class ExecutionSandboxNode(GraphNode):
    registry: AgentRegistry = field(default_factory=build_default_agent_registry)
    sandbox_runner: SandboxRunner | None = None
    name: str = "execution_sandbox"

    def __post_init__(self) -> None:
        if self.sandbox_runner is None:
            self.sandbox_runner = SandboxRunner(registry=self.registry)

    def run(self, state: GraphState) -> NodeResult:
        tasks = state.plan.get("tasks", ())
        if not isinstance(tasks, (list, tuple)) or not tasks:
            raise ValueError("planner node must provide ordered tasks")

        sandbox_results: list[dict[str, Any]] = []
        for task in tasks:
            task_payload = dict(task)
            sandbox_results.append(
                self.sandbox_runner.run_task(
                    SandboxRunRequest(task=task_payload, run_id=state.run_id)
                ).to_dict()
            )

        failed = [item for item in sandbox_results if item["status"] != "succeeded"]
        next_status = GraphRunStatus.FAILED if failed else state.status
        return NodeResult(
            state=state.with_updates(status=next_status, sandbox_results=tuple(sandbox_results)),
            explanation="Execution sandbox validated every task through the mandatory guard.",
            outputs={"sandbox_results": sandbox_results},
        )


@dataclass(slots=True)
class MemoryNode(GraphNode):
    memory_manager: MemoryManager = field(default_factory=MemoryManager)
    name: str = "memory"

    def run(self, state: GraphState) -> NodeResult:
        episode = self.memory_manager.append_episode(
            event_type="graph.execution",
            actor="core.graph",
            summary=f"Graph run {state.run_id} processed stimulus from {state.source}.",
            payload={
                "run_id": state.run_id,
                "stimulus": state.stimulus,
                "execution_path": state.execution_path,
                "task_ids": state.plan.get("ordered_task_ids", []),
                "sandbox_statuses": [
                    item.get("status") for item in state.sandbox_results
                ],
            },
            index=True,
        )
        fact = self.memory_manager.append_fact(
            subject=state.run_id,
            predicate="graph_status",
            value=(
                "sandbox_validated"
                if all(item.get("status") == "succeeded" for item in state.sandbox_results)
                else "sandbox_failed"
            ),
            confidence=1.0,
            source="core.graph.memory",
        )
        memory_payload = {
            "episode_id": episode.record_id,
            "semantic_fact_id": fact.record_id,
            "snapshot": self.memory_manager.snapshot(),
        }
        return NodeResult(
            state=state.with_updates(memory=memory_payload),
            explanation="Memory node appended episodic and semantic records without overwrites.",
            outputs={"memory": memory_payload},
        )


class ReflectionNode(GraphNode):
    name = "reflection"

    def run(self, state: GraphState) -> NodeResult:
        total = len(state.sandbox_results)
        successes = sum(1 for item in state.sandbox_results if item.get("status") == "succeeded")
        success_rate = 1.0 if total == 0 else round(successes / total, 3)
        issues = []
        if success_rate < 1.0:
            issues.append("One or more sandbox validations failed.")
        if len(state.execution_path) != len(set(state.execution_path)):
            issues.append("Graph path repeated a node unexpectedly.")
        reflection = {
            "success_rate": success_rate,
            "task_count": total,
            "completed_tasks": successes,
            "issues": issues,
            "score": round(0.5 + success_rate * 0.5, 3),
            "explanation": (
                "Reflection is deterministic: score is derived from sandbox success rate "
                "and graph path consistency."
            ),
        }
        return NodeResult(
            state=state.with_updates(reflection=reflection),
            explanation="Reflection evaluated graph execution using deterministic metrics.",
            outputs={"reflection": reflection},
        )


class OutputNode(GraphNode):
    name = "output"

    def run(self, state: GraphState) -> NodeResult:
        final_status = "succeeded" if not state.errors and state.reflection.get("success_rate") == 1.0 else "failed"
        output = {
            "run_id": state.run_id,
            "status": final_status,
            "stimulus": state.stimulus,
            "plan_id": state.plan.get("graph_id"),
            "task_ids": state.plan.get("ordered_task_ids", []),
            "execution_path": (*state.execution_path, self.name),
            "agent_assignments": tuple(dict(item) for item in state.assignments),
            "reflection": dict(state.reflection),
            "memory": dict(state.memory),
            "errors": tuple(error.to_dict() for error in state.errors),
            "explanation": "Output node synthesized the final traceable graph result.",
        }
        return NodeResult(
            state=state.with_updates(output=output),
            explanation="Output node produced the final structured graph response.",
            outputs={"output": output},
        )


__all__ = [
    "AgentDispatchNode",
    "ExecutionSandboxNode",
    "InputNode",
    "MemoryNode",
    "OutputNode",
    "PlannerNode",
    "ReflectionNode",
]
