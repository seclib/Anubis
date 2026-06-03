from __future__ import annotations

from typing import Protocol

from anubis.types import AgentContext, Plan, StepExecution, TaskSnapshot, Verification


class AgentLoop(Protocol):
    def run(self, task: TaskSnapshot) -> TaskSnapshot:
        ...

    def step(self, task: TaskSnapshot) -> StepExecution:
        ...

    def plan(self, task: TaskSnapshot, context: AgentContext) -> Plan:
        ...

    def verify(self, task: TaskSnapshot, execution: StepExecution) -> Verification:
        ...


__all__ = ["AgentLoop"]
