"""Distributed Executor Agent for ANUBIS Phase B3."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from anubis.distributed.execution_errors import (
    ExecutorAgentError,
    InvalidExecutionStepError,
)
from anubis.distributed.execution_logger import ExecutionLogEntry, InMemoryExecutionLogger
from anubis.distributed.tool_integration import ToolIntegrationLayer


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    tool: str
    tool_input: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionStep":
        step_id = payload.get("step_id") or payload.get("id")
        tool = payload.get("tool")
        tool_input = payload.get("input", payload.get("tool_input", {}))

        if not isinstance(step_id, str) or not step_id.strip():
            raise InvalidExecutionStepError("execution step requires a non-empty step_id")
        if not isinstance(tool, str) or not tool.strip():
            raise InvalidExecutionStepError("execution step requires a non-empty tool")
        if not isinstance(tool_input, Mapping):
            raise InvalidExecutionStepError("execution step input must be a mapping")

        return cls(step_id=step_id.strip(), tool=tool.strip(), tool_input=dict(tool_input))


@dataclass(frozen=True)
class ExecutionResult:
    step_id: str
    success: bool
    output: str
    logs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "output": self.output,
            "logs": list(self.logs),
        }


class ExecutorAgent:
    """Executes one assigned step through the tool system only."""

    def __init__(
        self,
        *,
        tools: ToolIntegrationLayer | None = None,
        logger: InMemoryExecutionLogger | None = None,
    ) -> None:
        self.tools = tools or ToolIntegrationLayer()
        self.logger = logger or InMemoryExecutionLogger()

    def execute(self, step: ExecutionStep | Mapping[str, Any]) -> ExecutionResult:
        try:
            execution_step = step if isinstance(step, ExecutionStep) else ExecutionStep.from_mapping(step)
        except InvalidExecutionStepError as exc:
            logs = [f"{exc.__class__.__name__}: {exc}"]
            return ExecutionResult(
                step_id=str(step.get("step_id") or step.get("id") or "") if isinstance(step, Mapping) else "",
                success=False,
                output=str(exc),
                logs=tuple(logs),
            )

        logs = [f"executor_agent received step {execution_step.step_id}"]

        try:
            tool_result = self.tools.execute(execution_step.tool, execution_step.tool_input)
            success = bool(tool_result.get("success", False))
            output = self._string_output(tool_result.get("output", ""))
            tool_logs = tool_result.get("logs", [])
            if isinstance(tool_logs, list):
                logs.extend(str(entry) for entry in tool_logs)
            logs.append(f"tool {execution_step.tool} completed success={success}")
        except ExecutorAgentError as exc:
            success = False
            output = str(exc)
            logs.append(f"{exc.__class__.__name__}: {exc}")
        except Exception as exc:
            success = False
            output = str(exc)
            logs.append(f"Unhandled executor error: {exc.__class__.__name__}: {exc}")

        self.logger.record(
            ExecutionLogEntry(
                step_id=execution_step.step_id,
                tool=execution_step.tool,
                success=success,
                message=output,
            )
        )
        return ExecutionResult(
            step_id=execution_step.step_id,
            success=success,
            output=output,
            logs=tuple(logs),
        )

    def execute_dict(self, step: ExecutionStep | Mapping[str, Any]) -> dict[str, Any]:
        return self.execute(step).to_dict()

    def _string_output(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        return json.dumps(output, sort_keys=True, default=str)


__all__ = ["ExecutionResult", "ExecutionStep", "ExecutorAgent"]
