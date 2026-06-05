from __future__ import annotations

import sys as _sys


def _load_stdlib_types() -> dict[str, object]:
    path = f"{_sys.base_prefix}/lib/python{_sys.version_info.major}.{_sys.version_info.minor}/types.py"
    namespace: dict[str, object] = {
        "__builtins__": __builtins__,
        "__file__": path,
        "__name__": "_stdlib_types",
    }
    try:
        with open(path, "r", encoding="utf-8") as handle:
            exec(compile(handle.read(), path, "exec"), namespace)
    except OSError:
        return {}
    return namespace


_STDLIB_TYPES = _load_stdlib_types()

for _name, _value in _STDLIB_TYPES.items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)


if __name__ == "types":
    __all__ = list(_STDLIB_TYPES.get("__all__", ()))
else:
    from dataclasses import dataclass, field
    from enum import StrEnum
    from typing import Any, Literal, Mapping, Protocol, TypedDict, TypeAlias

    JSONScalar: TypeAlias = str | int | float | bool | None
    JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
    JSONObject: TypeAlias = dict[str, JSONValue]

    class TaskStatus(StrEnum):
        PENDING = "pending"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    class AgentExecutionState(StrEnum):
        PLANNING = "planning"
        EXECUTING = "executing"
        VERIFYING = "verifying"
        RETRYING = "retrying"

    ToolName: TypeAlias = str
    ModelName: TypeAlias = str
    TaskId: TypeAlias = str

    class JSONSchema(TypedDict, total=False):
        type: str
        properties: dict[str, "JSONSchema"]
        required: list[str]
        items: "JSONSchema"
        additionalProperties: bool
        description: str

    class ToolCall(TypedDict):
        tool: ToolName
        input: JSONObject

    class ToolResult(TypedDict):
        tool: ToolName
        input: JSONObject
        output: JSONValue
        success: bool
        error: str | None
        logs: list[str]
        duration_ms: int

    class HistoryEvent(TypedDict):
        timestamp: str
        event: str
        payload: JSONObject

    class TaskSnapshot(TypedDict):
        id: TaskId
        goal: str
        status: Literal["pending", "running", "done", "failed"]
        context: JSONObject
        plan: JSONObject
        history: list[HistoryEvent]

    @dataclass(frozen=True)
    class ContextChunk:
        path: str
        text: str
        score: float
        metadata: JSONObject = field(default_factory=dict)

    @dataclass(frozen=True)
    class AgentContext:
        task_id: TaskId
        goal: str
        chunks: tuple[ContextChunk, ...]
        compressed: str
        metadata: JSONObject = field(default_factory=dict)

    @dataclass(frozen=True)
    class PlanStep:
        id: int
        goal: str
        tool: ToolName | None = None
        input: JSONObject = field(default_factory=dict)

    @dataclass(frozen=True)
    class Plan:
        task_id: TaskId
        goal: str
        steps: tuple[PlanStep, ...]
        metadata: JSONObject = field(default_factory=dict)

    @dataclass(frozen=True)
    class StepExecution:
        step: PlanStep
        result: ToolResult | None
        success: bool

    @dataclass(frozen=True)
    class Verification:
        success: bool
        retry: bool
        reason: str
        metadata: JSONObject = field(default_factory=dict)

    class Serializable(Protocol):
        def to_dict(self) -> Mapping[str, Any]:
            ...

    __all__ = [
        "AgentContext",
        "AgentExecutionState",
        "ContextChunk",
        "HistoryEvent",
        "JSONObject",
        "JSONScalar",
        "JSONSchema",
        "JSONValue",
        "ModelName",
        "Plan",
        "PlanStep",
        "Serializable",
        "StepExecution",
        "TaskId",
        "TaskSnapshot",
        "TaskStatus",
        "ToolCall",
        "ToolName",
        "ToolResult",
        "Verification",
    ]
