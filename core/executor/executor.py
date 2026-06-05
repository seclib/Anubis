from __future__ import annotations

from dataclasses import dataclass

from anubis.tools import ToolExecutionEngine, create_default_tool_engine
from anubis.types import Plan, PlanStep, StepExecution, ToolResult


@dataclass(frozen=True)
class PlanExecution:
    steps: tuple[StepExecution, ...]

    @property
    def success(self) -> bool:
        return all(step.success for step in self.steps)


class ToolDrivenExecutor:
    def __init__(self, tools: ToolExecutionEngine | None = None) -> None:
        self.tools = tools or create_default_tool_engine()

    def execute_plan(self, plan: Plan) -> PlanExecution:
        return PlanExecution(tuple(self.execute_step(step) for step in plan.steps))

    def execute_step(self, step: PlanStep) -> StepExecution:
        result = self.execute_tool_step(step)
        return StepExecution(step=step, result=result, success=bool(result["success"]))

    def execute_tool_step(self, step: PlanStep) -> ToolResult:
        if step.tool is None:
            return {
                "tool": "",
                "input": step.input,
                "output": {"type": "ToolRequiredError"},
                "success": False,
                "error": "agent steps must execute through tools",
                "logs": [],
                "duration_ms": 0,
            }
        return self.tools.execute(step.tool, step.input)


__all__ = ["PlanExecution", "ToolDrivenExecutor"]
