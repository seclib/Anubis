"""Interchangeable agent pool for ANUBIS swarm coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core.agents import AgentRegistry, BaseAgent, build_default_agent_registry


@dataclass(frozen=True, slots=True)
class SwarmAgentDescriptor:
    name: str
    role: str
    capabilities: frozenset[str]
    score: float = 0.5

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("agent name cannot be empty")
        if not self.role.strip():
            raise ValueError("agent role cannot be empty")
        if not 0 <= self.score <= 1:
            raise ValueError("agent score must be between 0 and 1")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "role", self.role.strip())
        object.__setattr__(
            self,
            "capabilities",
            frozenset(sorted(capability.strip() for capability in self.capabilities if capability.strip())),
        )

    @classmethod
    def from_agent(cls, agent: BaseAgent, *, score: float = 0.5) -> "SwarmAgentDescriptor":
        return cls(
            name=agent.name,
            role=agent.role,
            capabilities=agent.capabilities,
            score=score,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "capabilities": sorted(self.capabilities),
            "score": self.score,
        }


class AgentPool:
    """Deterministic facade for interchangeable stateless agents."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or build_default_agent_registry()
        self._scores: dict[str, float] = {}

    def descriptors(self) -> tuple[SwarmAgentDescriptor, ...]:
        return tuple(
            SwarmAgentDescriptor.from_agent(agent, score=self._scores.get(agent.name, 0.5))
            for agent in sorted(self.registry.agents.values(), key=lambda item: item.name)
        )

    def replace(self, old_name: str, new_agent: BaseAgent, *, score: float = 0.5) -> None:
        if old_name in self.registry.agents:
            del self.registry.agents[old_name]
        self.registry.register(new_agent)
        self._scores[new_agent.name] = score

    def update_score(self, agent_name: str, delta: float) -> float:
        current = self._scores.get(agent_name, 0.5)
        next_score = round(min(1.0, max(0.0, current + delta)), 3)
        self._scores[agent_name] = next_score
        return next_score

    def select(self, *, role: str | None = None, capability: str | None = None) -> BaseAgent:
        candidates = list(self.registry.agents.values())
        if role is not None:
            candidates = [agent for agent in candidates if agent.role == role]
        if capability is not None:
            candidates = [agent for agent in candidates if capability in agent.capabilities]
        if not candidates:
            raise LookupError("no swarm agent matches requested role/capability")
        return sorted(
            candidates,
            key=lambda agent: (-self._scores.get(agent.name, 0.5), agent.name),
        )[0]

    def run(self, agent_name: str, payload: Mapping[str, object]) -> dict[str, object]:
        return self.registry.run(agent_name, payload)


__all__ = ["AgentPool", "SwarmAgentDescriptor"]
