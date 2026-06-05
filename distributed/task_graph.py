"""Task graph structures for dependency-based ANUBIS execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskGraphNodeType(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"


class TaskGraphNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TaskGraphNode:
    id: str
    type: TaskGraphNodeType
    depends_on: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "type": self.type.value,
            "depends_on": list(self.depends_on),
        }
        if self.payload:
            payload["payload"] = dict(self.payload)
        return payload


@dataclass(frozen=True)
class TaskGraph:
    task_id: str
    nodes: tuple[TaskGraphNode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "nodes": [node.to_dict() for node in self.nodes],
        }

    def node_map(self) -> dict[str, TaskGraphNode]:
        return {node.id: node for node in self.nodes}


@dataclass(frozen=True)
class NodeExecutionResult:
    node_id: str
    success: bool
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class TaskGraphRun:
    task_id: str
    success: bool
    results: tuple[NodeExecutionResult, ...]
    groups: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "results": [result.to_dict() for result in self.results],
            "groups": [list(group) for group in self.groups],
        }


__all__ = [
    "NodeExecutionResult",
    "TaskGraph",
    "TaskGraphNode",
    "TaskGraphNodeStatus",
    "TaskGraphNodeType",
    "TaskGraphRun",
]
