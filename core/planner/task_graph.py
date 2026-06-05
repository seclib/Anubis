"""Immutable task graph data structures for ANUBIS planning.

The planner owns only structure and ordering. It never executes work, calls
agents, or mutates runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _freeze_strings(values: tuple[str, ...] | frozenset[str] | set[str] | list[str]) -> frozenset[str]:
    normalized = {item.strip() for item in values if item and item.strip()}
    return frozenset(sorted(normalized))


@dataclass(frozen=True, slots=True)
class InputIntent:
    """Structured intent inferred from user input."""

    kind: str
    objective: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        kind = self.kind.strip()
        objective = self.objective.strip()
        if not kind:
            raise ValueError("intent kind cannot be empty")
        if not objective:
            raise ValueError("intent objective cannot be empty")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskNode:
    """A single planned task with dependency and capability metadata."""

    task_id: str
    kind: str
    objective: str
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    depends_on: frozenset[str] = field(default_factory=frozenset)
    priority: int = 100
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        task_id = self.task_id.strip()
        kind = self.kind.strip()
        objective = self.objective.strip()
        if not task_id:
            raise ValueError("task_id cannot be empty")
        if not kind:
            raise ValueError(f"task {task_id} kind cannot be empty")
        if not objective:
            raise ValueError(f"task {task_id} objective cannot be empty")
        if self.priority < 1:
            raise ValueError(f"task {task_id} priority must be positive")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "required_capabilities", _freeze_strings(self.required_capabilities))
        object.__setattr__(self, "depends_on", _freeze_strings(self.depends_on))
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskGraph:
    """A dependency graph produced by the planner."""

    graph_id: str
    intent: InputIntent
    nodes: tuple[TaskNode, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        graph_id = self.graph_id.strip()
        if not graph_id:
            raise ValueError("graph_id cannot be empty")
        if not self.nodes:
            raise ValueError("task graph must contain at least one node")
        object.__setattr__(self, "graph_id", graph_id)
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(node.task_id for node in self.nodes)

    def get(self, task_id: str) -> TaskNode:
        for node in self.nodes:
            if node.task_id == task_id:
                return node
        raise KeyError(f"unknown task id: {task_id}")

    def dependencies_of(self, task_id: str) -> tuple[TaskNode, ...]:
        node = self.get(task_id)
        return tuple(self.get(dep_id) for dep_id in sorted(node.depends_on))

    def dependents_of(self, task_id: str) -> tuple[TaskNode, ...]:
        return tuple(node for node in self.nodes if task_id in node.depends_on)


@dataclass(frozen=True, slots=True)
class OrderedExecutionPlan:
    """A deterministic topological ordering of a task graph."""

    graph: TaskGraph
    ordered_tasks: tuple[TaskNode, ...]
    explanation: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ordered_tasks", tuple(self.ordered_tasks))
        object.__setattr__(self, "explanation", tuple(self.explanation))

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(task.task_id for task in self.ordered_tasks)


__all__ = ["InputIntent", "OrderedExecutionPlan", "TaskGraph", "TaskNode"]
