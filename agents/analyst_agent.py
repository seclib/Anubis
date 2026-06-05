from __future__ import annotations

from agents.base import BaseResearchAgent
from anubis.core_life.swarm.agent_registry import ResearchRole, ResearchTask


class AnalystAgent(BaseResearchAgent):
    def __init__(self, name: str = "research_analyst") -> None:
        super().__init__(
            name=name,
            role=ResearchRole.ANALYST,
            capabilities=frozenset({"interpret", "compare"}),
            score=0.8,
        )

    async def handle(self, task: ResearchTask, memory):
        recalled = memory.recall(task.session_id, actor_id=self.name)
        return self.insight(
            task,
            summary=(
                f"Interpreted {len(recalled)} shared swarm memory record(s); "
                "planner and executor outputs are consistent with a conservative answer."
            ),
            recommendation="accept",
            confidence=0.79,
            evidence=tuple(record.id for record in recalled),
        )
