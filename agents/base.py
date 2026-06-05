from __future__ import annotations

from dataclasses import dataclass

from anubis.core_life.swarm.agent_registry import (
    AgentInsight,
    ResearchAgentDescriptor,
    ResearchRole,
    ResearchTask,
)


@dataclass(slots=True)
class BaseResearchAgent:
    name: str
    role: ResearchRole
    capabilities: frozenset[str]
    score: float = 0.7

    @property
    def descriptor(self) -> ResearchAgentDescriptor:
        return ResearchAgentDescriptor(
            name=self.name,
            role=self.role,
            capabilities=self.capabilities,
            score=self.score,
        )

    def insight(
        self,
        task: ResearchTask,
        *,
        summary: str,
        recommendation: str,
        confidence: float,
        evidence: tuple[str, ...],
    ) -> AgentInsight:
        return AgentInsight(
            agent_name=self.name,
            role=self.role,
            task_id=task.id,
            summary=summary,
            recommendation=recommendation,
            confidence=confidence,
            evidence=evidence,
        )
