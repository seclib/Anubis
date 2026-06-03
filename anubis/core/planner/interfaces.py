from __future__ import annotations

from typing import Protocol

from anubis.types import AgentContext, Plan, TaskSnapshot


class Planner(Protocol):
    def plan(self, task: TaskSnapshot, context: AgentContext) -> Plan:
        ...


__all__ = ["Planner"]
