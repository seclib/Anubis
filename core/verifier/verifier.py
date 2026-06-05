from __future__ import annotations

from anubis.core.executor.executor import PlanExecution
from anubis.types import StepExecution, TaskSnapshot, ToolResult, Verification


class DefaultVerifier:
    def validate_file_state(self, result: ToolResult) -> Verification:
        if not result["success"]:
            return Verification(False, True, result["error"] or "file tool failed")
        output = result["output"]
        if not isinstance(output, dict):
            return Verification(False, True, "file tool returned non-object output")
        if result["tool"] == "read_file" and "content" not in output:
            return Verification(False, True, "read_file output missing content")
        if result["tool"] == "write_file" and "bytes" not in output:
            return Verification(False, True, "write_file output missing byte count")
        return Verification(True, False, "file state verified")

    def validate_command_output(self, result: ToolResult) -> Verification:
        if not result["success"]:
            return Verification(False, True, result["error"] or "command tool failed")
        output = result["output"]
        if isinstance(output, dict) and int(output.get("code", 0)) != 0:
            return Verification(False, True, f"command exited with code {output.get('code')}")
        return Verification(True, False, "command output verified")

    def validate_task_success(self, task: TaskSnapshot, execution: StepExecution) -> Verification:
        result = execution.result
        if result is None:
            return Verification(False, True, "missing tool result")
        if result["tool"] in {"read_file", "write_file"}:
            return self.validate_file_state(result)
        if result["tool"] in {"run_command", "git_diff", "git_commit"}:
            return self.validate_command_output(result)
        if not execution.success:
            return Verification(False, True, result["error"] or "step failed")
        return Verification(True, False, "step verified")

    def verify_plan(self, task: TaskSnapshot, execution: PlanExecution) -> Verification:
        if not execution.steps:
            return Verification(False, False, "planner produced no executable tool steps")
        for step in execution.steps:
            verification = self.validate_task_success(task, step)
            if not verification.success:
                return verification
        return Verification(True, False, "plan verified")


__all__ = ["DefaultVerifier"]
