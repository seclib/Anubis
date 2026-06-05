from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4
from enum import StrEnum


class ResearchRole(StrEnum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    ANALYST = "analyst"
    CRITIC = "critic"
    SYNTHESIZER = "synthesizer"


@dataclass(frozen=True, slots=True)
class ResearchTask:
    stimulus: str
    role: ResearchRole
    session_id: str
    context: Mapping[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"research_task_{uuid4().hex}")

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True, slots=True)
class AgentInsight:
    agent_name: str
    role: ResearchRole
    task_id: str
    summary: str
    recommendation: str
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ResearchAgentDescriptor:
    name: str
    role: ResearchRole
    capabilities: frozenset[str]
    score: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 1:
            raise ValueError("score must be between 0 and 1")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


class ResearchAgent(Protocol):
    @property
    def descriptor(self) -> ResearchAgentDescriptor:
        raise NotImplementedError

    async def handle(self, task: ResearchTask, memory: Any) -> AgentInsight:
        raise NotImplementedError


class ResearchAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, ResearchAgent] = {}
        self._scores: dict[str, float] = {}

    def register(self, agent: ResearchAgent) -> None:
        descriptor = agent.descriptor
        if descriptor.name in self._agents:
            raise ValueError(f"research agent already registered: {descriptor.name}")
        self._agents[descriptor.name] = agent
        self._scores[descriptor.name] = descriptor.score

    def agent(self, name: str) -> ResearchAgent:
        return self._agents[name]

    def agents_for_role(self, role: ResearchRole) -> tuple[ResearchAgent, ...]:
        return tuple(
            sorted(
                (agent for agent in self._agents.values() if agent.descriptor.role == role),
                key=lambda agent: (-self.score(agent.descriptor.name), agent.descriptor.name),
            )
        )

    def descriptors(self) -> tuple[ResearchAgentDescriptor, ...]:
        return tuple(
            sorted(
                (
                    ResearchAgentDescriptor(
                        name=agent.descriptor.name,
                        role=agent.descriptor.role,
                        capabilities=agent.descriptor.capabilities,
                        score=self.score(agent.descriptor.name),
                    )
                    for agent in self._agents.values()
                ),
                key=lambda descriptor: (descriptor.role, descriptor.name),
            )
        )

    def score(self, agent_name: str) -> float:
        return self._scores.get(agent_name, 0.5)

    def update_score(self, agent_name: str, delta: float) -> float:
        next_score = min(1.0, max(0.0, self.score(agent_name) + delta))
        self._scores[agent_name] = next_score
        return next_score
