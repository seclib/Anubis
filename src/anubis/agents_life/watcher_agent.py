"""Observation-focused living agent."""

from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.types import AgentRunResult, Task


class WatcherAgent(BaseLivingAgent):
    def __init__(self, name: str = "watcher") -> None:
        super().__init__(name=name, capabilities=frozenset({"telemetry.read", "observe"}))

    async def handle(self, task: Task) -> AgentRunResult:
        objective = task.payload.get("objective", "unknown objective")
        return self.ok(
            task,
            action="collect_context",
            explanation="Collected local synthetic telemetry for the requested objective.",
            data={
                "objective": objective,
                "signals": (
                    "event_rate=medium",
                    "auth_failures=low",
                    "sandbox_denials=none",
                ),
                "traceable": True,
            },
        )
