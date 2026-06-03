from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

NodeType = Literal["command", "agent", "pipeline", "swarm", "tool"]


@dataclass(frozen=True)
class CommandNode:
    type: Literal["command"] = "command"
    command: str = ""
    args: str = ""
    argv: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentNode:
    type: Literal["agent"] = "agent"
    agent: str = ""
    task: Any = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolNode:
    type: Literal["tool"] = "tool"
    tool: str = ""
    action: str = ""
    args: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PipelineNode:
    type: Literal["pipeline"] = "pipeline"
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SwarmNode:
    type: Literal["swarm"] = "swarm"
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "AgentNode",
    "CommandNode",
    "NodeType",
    "PipelineNode",
    "SwarmNode",
    "ToolNode",
]
