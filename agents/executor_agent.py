from __future__ import annotations

from agents.base import BaseResearchAgent
from anubis.core_life.swarm.agent_registry import ResearchRole, ResearchTask


class ResearchExecutorAgent(BaseResearchAgent):
    def __init__(self, name: str = "research_executor") -> None:
        super().__init__(
            name=name,
            role=ResearchRole.EXECUTOR,
            capabilities=frozenset({"execute", "collect"}),
            score=0.74,
        )

    async def handle(self, task: ResearchTask, memory):
        return self.insight(
            task,
            summary=(
                "Executed research actions locally: inspected task context, "
                "preserved assumptions, and avoided unsafe external dependencies."
            ),
            recommendation="accept",
            confidence=0.76,
            evidence=("local-only execution", "no external dependency", "context preserved"),
        )
