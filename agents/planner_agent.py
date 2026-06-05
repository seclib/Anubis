from __future__ import annotations

from agents.base import BaseResearchAgent
from anubis.core_life.swarm.agent_registry import ResearchRole, ResearchTask


class PlannerAgent(BaseResearchAgent):
    def __init__(self, name: str = "research_planner") -> None:
        super().__init__(
            name=name,
            role=ResearchRole.PLANNER,
            capabilities=frozenset({"decompose", "strategy"}),
            score=0.78,
        )

    async def handle(self, task: ResearchTask, memory) :
        steps = (
            "clarify objective",
            "collect available evidence",
            "interpret evidence",
            "criticize assumptions",
            "synthesize final answer",
        )
        return self.insight(
            task,
            summary=f"Plan for '{task.stimulus}': " + "; ".join(steps),
            recommendation="accept",
            confidence=0.82,
            evidence=steps,
        )
