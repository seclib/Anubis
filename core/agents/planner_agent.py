"""Planner agent: converts an objective into a structured task plan."""

from __future__ import annotations

from core.agents.base_agent import AgentDescriptor, BaseAgent, StructuredDict
from core.planner import PlanningEngine


class PlannerAgent(BaseAgent):
    """Single-responsibility agent for deterministic task planning."""

    def __init__(self) -> None:
        super().__init__(
            descriptor=AgentDescriptor(
                name="planner_agent",
                role="planner",
                capabilities=frozenset({"planning.create_graph", "planning.order_tasks"}),
                description="Converts structured objectives into ordered task graphs.",
            )
        )

    def handle(self, input_data: StructuredDict) -> StructuredDict:
        objective = self.require_string(input_data, "objective")
        intent_kind = input_data.get("intent_kind", "investigate_alert")
        if not isinstance(intent_kind, str):
            intent_kind = "investigate_alert"

        plan = PlanningEngine().plan(objective, intent_kind=intent_kind)
        return {
            "intent": {
                "kind": plan.graph.intent.kind,
                "objective": plan.graph.intent.objective,
                "metadata": dict(plan.graph.intent.metadata),
            },
            "task_graph": {
                "graph_id": plan.graph.graph_id,
                "task_ids": list(plan.graph.task_ids),
                "tasks": [
                    {
                        "task_id": task.task_id,
                        "kind": task.kind,
                        "objective": task.objective,
                        "required_capabilities": sorted(task.required_capabilities),
                        "depends_on": sorted(task.depends_on),
                        "priority": task.priority,
                        "reason": task.reason,
                        "metadata": dict(task.metadata),
                    }
                    for task in plan.graph.nodes
                ],
            },
            "ordered_execution_plan": {
                "task_ids": list(plan.task_ids),
                "explanation": list(plan.explanation),
            },
        }


__all__ = ["PlannerAgent"]
