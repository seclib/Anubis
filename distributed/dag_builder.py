"""Build and validate deterministic task DAGs from planner output."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from anubis.distributed.dependency_resolver import DependencyResolutionError
from anubis.distributed.planning_schema import ExecutionPlan, PlanStep, PlanStepType
from anubis.distributed.task_graph import TaskGraph, TaskGraphNode, TaskGraphNodeType


class TaskGraphError(ValueError):
    """Raised when a task graph is invalid."""


class DAGBuilder:
    """Converts planner output into a DAG with deterministic ordering."""

    PLAN_NODE_ID = "plan"
    VERIFY_NODE_ID = "verify"

    def from_plan(self, plan: ExecutionPlan | Mapping[str, Any]) -> TaskGraph:
        execution_plan = plan if isinstance(plan, ExecutionPlan) else self._plan_from_mapping(plan)
        step_ids = {step.id for step in execution_plan.steps}
        nodes: list[TaskGraphNode] = [
            TaskGraphNode(
                id=self.PLAN_NODE_ID,
                type=TaskGraphNodeType.PLAN,
                payload={"task_id": execution_plan.task_id},
            )
        ]

        for step in execution_plan.steps:
            dependencies = step.depends_on or (self.PLAN_NODE_ID,)
            missing = [dependency for dependency in dependencies if dependency not in step_ids and dependency != self.PLAN_NODE_ID]
            if missing:
                raise TaskGraphError(
                    f"Step {step.id} depends on unknown nodes: {', '.join(missing)}"
                )
            nodes.append(
                TaskGraphNode(
                    id=step.id,
                    type=TaskGraphNodeType.EXECUTE,
                    depends_on=tuple(dependencies),
                    payload={
                        "action": step.action,
                        "step_type": step.type.value,
                    },
                )
            )

        terminal_ids = self._terminal_step_ids(execution_plan.steps)
        nodes.append(
            TaskGraphNode(
                id=self.VERIFY_NODE_ID,
                type=TaskGraphNodeType.VERIFY,
                depends_on=terminal_ids or (self.PLAN_NODE_ID,),
                payload={"task_id": execution_plan.task_id},
            )
        )

        graph = TaskGraph(task_id=execution_plan.task_id, nodes=tuple(nodes))
        self.validate(graph)
        return graph

    def validate(self, graph: TaskGraph) -> TaskGraph:
        ids = [node.id for node in graph.nodes]
        if len(ids) != len(set(ids)):
            raise TaskGraphError("Task graph node ids must be unique")
        known = set(ids)
        for node in graph.nodes:
            if node.id in node.depends_on:
                raise TaskGraphError(f"Node cannot depend on itself: {node.id}")
            missing = [dependency for dependency in node.depends_on if dependency not in known]
            if missing:
                raise TaskGraphError(
                    f"Node {node.id} depends on unknown nodes: {', '.join(missing)}"
                )
        self.topological_groups(graph)
        return graph

    def topological_order(self, graph: TaskGraph) -> tuple[TaskGraphNode, ...]:
        return tuple(node for group in self.topological_groups(graph) for node in group)

    def topological_groups(self, graph: TaskGraph) -> tuple[tuple[TaskGraphNode, ...], ...]:
        by_id = graph.node_map()
        dependents: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
        indegree: dict[str, int] = {node.id: len(node.depends_on) for node in graph.nodes}

        for node in graph.nodes:
            for dependency in node.depends_on:
                if dependency not in dependents:
                    raise TaskGraphError(f"Node {node.id} depends on unknown node: {dependency}")
                dependents[dependency].append(node.id)

        ready = deque(node.id for node in graph.nodes if indegree[node.id] == 0)
        completed = 0
        groups: list[tuple[TaskGraphNode, ...]] = []

        while ready:
            current_ids = tuple(ready)
            ready.clear()
            groups.append(tuple(by_id[node_id] for node_id in current_ids))
            completed += len(current_ids)
            for node_id in current_ids:
                for dependent_id in dependents[node_id]:
                    indegree[dependent_id] -= 1
                    if indegree[dependent_id] == 0:
                        ready.append(dependent_id)

        if completed != len(graph.nodes):
            raise TaskGraphError("Task graph dependencies contain a cycle")
        return tuple(groups)

    def _terminal_step_ids(self, steps: tuple[PlanStep, ...]) -> tuple[str, ...]:
        dependencies = {dependency for step in steps for dependency in step.depends_on}
        terminals = tuple(step.id for step in steps if step.id not in dependencies)
        return terminals

    def _plan_from_mapping(self, payload: Mapping[str, Any]) -> ExecutionPlan:
        task_id = payload.get("task_id")
        raw_steps = payload.get("steps")
        if not isinstance(task_id, str) or not task_id.strip():
            raise TaskGraphError("planner output requires a non-empty task_id")
        if not isinstance(raw_steps, list):
            raise TaskGraphError("planner output requires a steps list")

        steps: list[PlanStep] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, Mapping):
                raise TaskGraphError("planner steps must be objects")
            step_id = raw_step.get("id")
            action = raw_step.get("action")
            depends_on = raw_step.get("depends_on", [])
            step_type = raw_step.get("type")
            if not isinstance(step_id, str) or not step_id.strip():
                raise TaskGraphError("planner step requires a non-empty id")
            if not isinstance(action, str) or not action.strip():
                raise TaskGraphError(f"planner step {step_id} requires an action")
            if not isinstance(depends_on, list):
                raise TaskGraphError(f"planner step {step_id} depends_on must be a list")
            try:
                normalized_type = PlanStepType(str(step_type))
            except ValueError as exc:
                raise TaskGraphError(f"planner step {step_id} has invalid type: {step_type}") from exc
            steps.append(
                PlanStep(
                    id=step_id.strip(),
                    action=action.strip(),
                    depends_on=tuple(str(dependency) for dependency in depends_on),
                    type=normalized_type,
                )
            )

        try:
            graph = ExecutionPlan(task_id=task_id.strip(), steps=tuple(steps))
            self._validate_plan_dependencies(graph)
            return graph
        except DependencyResolutionError as exc:
            raise TaskGraphError(str(exc)) from exc

    def _validate_plan_dependencies(self, plan: ExecutionPlan) -> None:
        ids = [step.id for step in plan.steps]
        if len(ids) != len(set(ids)):
            raise DependencyResolutionError("Plan step ids must be unique")
        known = set(ids)
        for step in plan.steps:
            if step.id in step.depends_on:
                raise DependencyResolutionError(f"Step cannot depend on itself: {step.id}")
            missing = [dependency for dependency in step.depends_on if dependency not in known]
            if missing:
                raise DependencyResolutionError(
                    f"Step {step.id} depends on unknown steps: {', '.join(missing)}"
                )


__all__ = ["DAGBuilder", "TaskGraphError"]
