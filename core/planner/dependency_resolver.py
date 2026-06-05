"""Deterministic dependency resolution for ANUBIS task graphs."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.planner.task_graph import OrderedExecutionPlan, TaskGraph, TaskNode
from core.planner.validator import PlanValidationError, PlanValidator


class DependencyResolutionError(PlanValidationError):
    """Raised when dependencies cannot be resolved into a complete order."""


@dataclass(frozen=True, slots=True)
class DependencyResolver:
    """Topologically sorts task graphs without executing any task."""

    validator: PlanValidator = field(default_factory=PlanValidator)

    def resolve(self, graph: TaskGraph) -> OrderedExecutionPlan:
        self.validator.validate_graph(graph)

        remaining: dict[str, TaskNode] = {node.task_id: node for node in graph.nodes}
        dependency_ids: dict[str, set[str]] = {
            node.task_id: set(node.depends_on) for node in graph.nodes
        }
        dependents: dict[str, set[str]] = {node.task_id: set() for node in graph.nodes}
        for node in graph.nodes:
            for dep_id in node.depends_on:
                dependents[dep_id].add(node.task_id)

        ordered: list[TaskNode] = []
        explanation: list[str] = [
            f"Resolved graph {graph.graph_id} for intent {graph.intent.kind}.",
            "Ordering rule: all dependencies first, then lower priority value, then task id.",
        ]

        ready = self._ready_nodes(remaining, dependency_ids)
        while ready:
            current = ready[0]
            ordered.append(current)
            explanation.append(
                f"Selected {current.task_id}: dependencies satisfied "
                f"({', '.join(sorted(current.depends_on)) or 'none'})."
            )
            del remaining[current.task_id]

            for dependent_id in sorted(dependents[current.task_id]):
                dependency_ids[dependent_id].discard(current.task_id)

            ready = self._ready_nodes(remaining, dependency_ids)

        if remaining:
            blocked = ", ".join(sorted(remaining))
            raise DependencyResolutionError(f"cycle or unresolved dependency detected: {blocked}")

        plan = OrderedExecutionPlan(
            graph=graph,
            ordered_tasks=tuple(ordered),
            explanation=tuple(explanation),
        )
        self.validator.validate_order(plan)
        return plan

    @staticmethod
    def _ready_nodes(
        remaining: dict[str, TaskNode],
        dependency_ids: dict[str, set[str]],
    ) -> list[TaskNode]:
        ready = [
            node for task_id, node in remaining.items() if not dependency_ids[task_id]
        ]
        return sorted(ready, key=lambda node: (node.priority, node.task_id))


__all__ = ["DependencyResolutionError", "DependencyResolver"]
