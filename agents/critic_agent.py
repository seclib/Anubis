from __future__ import annotations

from agents.base import BaseResearchAgent
from anubis.core_life.swarm.agent_registry import ResearchRole, ResearchTask


class CriticAgent(BaseResearchAgent):
    def __init__(self, name: str = "research_critic") -> None:
        super().__init__(
            name=name,
            role=ResearchRole.CRITIC,
            capabilities=frozenset({"critique", "risk"}),
            score=0.77,
        )

    async def handle(self, task: ResearchTask, memory):
        recalled = memory.recall(task.session_id, actor_id=self.name)
        missing = "insufficient evidence" if not recalled else "no blocking flaw"
        recommendation = "revise" if not recalled else "accept"
        confidence = 0.55 if not recalled else 0.72
        return self.insight(
            task,
            summary=f"Critique complete: {missing}; require traceable synthesis.",
            recommendation=recommendation,
            confidence=confidence,
            evidence=tuple(record.id for record in recalled),
        )
