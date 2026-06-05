"""Graph node contract for ANUBIS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.graph.state import GraphState, freeze_mapping


@dataclass(frozen=True, slots=True)
class NodeResult:
    state: GraphState
    explanation: str
    outputs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.explanation.strip():
            raise ValueError("node explanation cannot be empty")
        object.__setattr__(self, "explanation", self.explanation.strip())
        object.__setattr__(self, "outputs", freeze_mapping(self.outputs))


class GraphNode(ABC):
    """Single-responsibility state transition unit."""

    name: str

    @abstractmethod
    def run(self, state: GraphState) -> NodeResult:
        """Return the next graph state."""


__all__ = ["GraphNode", "NodeResult"]
