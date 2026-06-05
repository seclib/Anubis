"""Reasoning-focused living agent."""

from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.types import AgentRunResult, Task


class ThinkerAgent(BaseLivingAgent):
    def __init__(self, name: str = "thinker") -> None:
        super().__init__(name=name, capabilities=frozenset({"reason.plan", "triage"}))

    async def handle(self, task: Task) -> AgentRunResult:
        objective = task.payload.get("objective", "unknown objective")
        return self.ok(
            task,
            action="analyze_evidence",
            explanation="Built a conservative hypothesis from available evidence.",
            data={
                "objective": objective,
                "hypothesis": "No critical compromise indicators in local synthetic evidence.",
                "confidence": 0.72,
                "next_step": "recommend_response",
            },
        )
