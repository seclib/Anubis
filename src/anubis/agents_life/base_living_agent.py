"""Base living agent contract."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from anubis.types import AgentDescriptor, AgentRunResult, Task


@dataclass(slots=True)
class BaseLivingAgent:
    name: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        self.capabilities = frozenset(self.capabilities)

    def descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            capabilities=self.capabilities,
            version=self.version,
        )

    async def handle(self, task: Task) -> AgentRunResult:
        return self.ok(
            task,
            action="observe",
            explanation="Base agent acknowledged the task without specialized behavior.",
        )

    def ok(
        self,
        task: Task,
        *,
        action: str,
        explanation: str,
        data: Mapping[str, Any] | None = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            {
                "agent": self.name,
                "task": task.kind,
                "action": action,
                "explanation": explanation,
                "data": dict(data or {}),
            }
        )
