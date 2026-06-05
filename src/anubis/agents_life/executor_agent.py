"""Execution-focused living agent."""

from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.types import AgentRunResult, Task


class ExecutorAgent(BaseLivingAgent):
    def __init__(self, name: str = "executor") -> None:
        super().__init__(name=name, capabilities=frozenset({"execute", "policy.evaluate"}))

    async def handle(self, task: Task) -> AgentRunResult:
        objective = task.payload.get("objective", "unknown objective")
        return self.ok(
            task,
            action="recommend_response",
            explanation="Recommended a local-first defensive response without unsafe execution.",
            data={
                "objective": objective,
                "recommendation": "increase monitoring, preserve evidence, avoid destructive action",
                "risk": "low",
                "safe_to_apply": True,
            },
        )
