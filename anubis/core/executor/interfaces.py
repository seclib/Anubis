from __future__ import annotations

from typing import Protocol

from anubis.types import PlanStep, StepExecution, ToolResult


class Executor(Protocol):
    def execute_step(self, step: PlanStep) -> StepExecution:
        ...

    def execute_tool_step(self, step: PlanStep) -> ToolResult:
        ...


__all__ = ["Executor"]
