"""Validation rules for planner-owned data structures."""

from __future__ import annotations

from dataclasses import dataclass

from core.planner.task_graph import OrderedExecutionPlan, TaskGraph


class PlanValidationError(ValueError):
    """Raised when a task graph or ordered plan is structurally invalid."""


@dataclass(frozen=True, slots=True)
class PlanValidator:
    """Pure validator with no execution or orchestration responsibilities."""

    def validate_graph(self, graph: TaskGraph) -> None:
        ids = graph.task_ids
        duplicate_ids = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        if duplicate_ids:
            raise PlanValidationError(f"duplicate task ids: {', '.join(duplicate_ids)}")

        known_ids = set(ids)
        for node in graph.nodes:
            if node.task_id in node.depends_on:
                raise PlanValidationError(f"task {node.task_id} cannot depend on itself")

            unknown = sorted(node.depends_on - known_ids)
            if unknown:
                raise PlanValidationError(
                    f"task {node.task_id} has unknown dependencies: {', '.join(unknown)}"
                )

    def validate_order(self, plan: OrderedExecutionPlan) -> None:
        self.validate_graph(plan.graph)

        graph_ids = set(plan.graph.task_ids)
        ordered_ids = plan.task_ids
        if set(ordered_ids) != graph_ids:
            missing = sorted(graph_ids - set(ordered_ids))
            extra = sorted(set(ordered_ids) - graph_ids)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if extra:
                details.append(f"extra: {', '.join(extra)}")
            raise PlanValidationError(f"ordered plan does not match graph ({'; '.join(details)})")

        positions = {task_id: index for index, task_id in enumerate(ordered_ids)}
        for node in plan.ordered_tasks:
            late_dependencies = sorted(
                dep_id for dep_id in node.depends_on if positions[dep_id] > positions[node.task_id]
            )
            if late_dependencies:
                raise PlanValidationError(
                    f"task {node.task_id} appears before dependencies: "
                    f"{', '.join(late_dependencies)}"
                )


__all__ = ["PlanValidationError", "PlanValidator"]
