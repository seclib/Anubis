from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from backend.agent.planner import PHASE1_TOOLS, Plan, PlanStep
from backend.tools import invoke_tool


ToolInvoker = Callable[[str, Mapping[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True)
class StepResult:
    step: PlanStep
    tool_result: dict[str, Any] | None
    validation: dict[str, Any]
    success: bool


@dataclass(frozen=True)
class ExecutionResult:
    plan: Plan
    steps: list[StepResult]

    @property
    def success(self) -> bool:
        return all(step.success for step in self.steps)


class Executor:
    def __init__(self, tool_invoker: ToolInvoker = invoke_tool) -> None:
        self.tool_invoker = tool_invoker

    def execute(self, plan: Plan) -> ExecutionResult:
        results = [self.execute_step(step) for step in plan.steps]
        return ExecutionResult(plan=plan, steps=results)

    def execute_step(self, step: PlanStep) -> StepResult:
        if step.tool is None:
            return StepResult(
                step=step,
                tool_result=None,
                validation={"success": True, "reason": "reasoning step"},
                success=True,
            )
        if step.tool not in PHASE1_TOOLS:
            return StepResult(
                step=step,
                tool_result={
                    "tool": step.tool,
                    "input": step.input,
                    "output": {
                        "error": f"Tool is outside Phase 1 scope: {step.tool}",
                        "type": "ToolScopeError",
                    },
                    "success": False,
                },
                validation={"success": False, "reason": "tool outside Phase 1 scope"},
                success=False,
            )
        result = self.tool_invoker(step.tool, step.input)
        validation = _validate_step_result(step.tool, result)
        return StepResult(
            step=step,
            tool_result=result,
            validation=validation,
            success=bool(result.get("success")) and bool(validation.get("success")),
        )


def _validate_step_result(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    from backend.agent.verifier import validate_command_output, validate_file_state

    if tool in {"read_file", "write_file"}:
        return validate_file_state(result)
    if tool in {"run_command", "git_diff", "git_commit"}:
        return validate_command_output(result)
    return {"success": bool(result.get("success")), "reason": "tool result accepted"}


__all__ = ["ExecutionResult", "Executor", "StepResult", "ToolInvoker"]
