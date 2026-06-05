from __future__ import annotations

from agents.base import BaseResearchAgent
from anubis.core_life.swarm.agent_registry import ResearchRole, ResearchTask


class SynthesizerAgent(BaseResearchAgent):
    def __init__(self, name: str = "research_synthesizer") -> None:
        super().__init__(
            name=name,
            role=ResearchRole.SYNTHESIZER,
            capabilities=frozenset({"synthesize", "decide"}),
            score=0.81,
        )

    async def handle(self, task: ResearchTask, memory):
        recalled = memory.recall(task.session_id, actor_id=self.name)
        summaries = tuple(record.content for record in recalled)
        return self.insight(
            task,
            summary=(
                f"Synthesized final research answer for '{task.stimulus}' from "
                f"{len(summaries)} swarm contribution(s)."
            ),
            recommendation="accept",
            confidence=0.84,
            evidence=tuple(record.id for record in recalled),
        )
