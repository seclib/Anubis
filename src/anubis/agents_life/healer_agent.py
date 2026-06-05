"""Recovery-focused living agent."""

from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.types import AgentRunResult, Task


class HealerAgent(BaseLivingAgent):
    def __init__(self, name: str = "healer") -> None:
        super().__init__(name=name, capabilities=frozenset({"recover", "rollback"}))

    async def handle(self, task: Task) -> AgentRunResult:
        return self.ok(
            task,
            action="recover",
            explanation="Prepared recovery guidance; no destructive recovery action executed.",
            data={"rollback_ready": True},
        )
