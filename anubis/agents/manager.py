from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any, TypeVar

from anubis.agents.base import Agent
from anubis.agents.registry import AgentRegistry
from anubis.agents.roles import ANALYST, BUILDER, ORCHESTRATOR, RESEARCHER

T = TypeVar("T")


class AgentManager:
    """High-level facade for agent lifecycle and state transitions."""

    def __init__(self, state: MutableMapping[str, Any] | None = None) -> None:
        self.registry = AgentRegistry(state)

    @property
    def states(self) -> dict[str, str]:
        return self.registry.snapshot()

    def list_agents(self) -> list[Agent]:
        return self.registry.list()

    def spawn(self, name: str) -> str:
        return self.registry.spawn(name)

    def update(self, name: str, state: str) -> None:
        self.registry.update(name, state)

    def run(self, name: str, action: Callable[[], T]) -> T:
        self.registry.update(name, "running")
        try:
            result = action()
        except Exception:
            self.registry.update(name, "idle")
            raise
        self.registry.update(name, "completed")
        return result


__all__ = [
    "ANALYST",
    "BUILDER",
    "ORCHESTRATOR",
    "RESEARCHER",
    "AgentManager",
]
