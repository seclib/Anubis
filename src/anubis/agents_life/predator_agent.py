"""Defensive agent for suppressing errors and anomalies."""

from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.types import AgentRunResult, Task


class PredatorAgent(BaseLivingAgent):
    def __init__(self, name: str = "predator") -> None:
        super().__init__(
            name=name,
            capabilities=frozenset({"defend", "anomaly.kill_switch", "policy.evaluate"}),
        )

    async def handle(self, task: Task) -> AgentRunResult:
        return self.ok(
            task,
            action="defend",
            explanation="Evaluated defensive posture and kept kill-switch armed but inactive.",
            data={"kill_switch": "armed", "triggered": False},
        )
