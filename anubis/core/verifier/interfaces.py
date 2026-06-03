from __future__ import annotations

from typing import Protocol

from anubis.types import StepExecution, TaskSnapshot, ToolResult, Verification


class Verifier(Protocol):
    def validate_file_state(self, result: ToolResult) -> Verification:
        ...

    def validate_command_output(self, result: ToolResult) -> Verification:
        ...

    def validate_task_success(self, task: TaskSnapshot, execution: StepExecution) -> Verification:
        ...


__all__ = ["Verifier"]
