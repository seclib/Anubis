from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from backend.agent.executor import ExecutionResult
from backend.tools.filesystem import resolve_project_path


@dataclass(frozen=True)
class VerificationResult:
    done: bool
    retry: bool
    reason: str


class Verifier:
    def verify(self, execution: ExecutionResult) -> VerificationResult:
        return validate_task_success(execution)


def validate_file_state(tool_result: Mapping[str, Any]) -> dict[str, Any]:
    if not tool_result.get("success"):
        return {"success": False, "reason": "file tool reported failure"}

    tool = str(tool_result.get("tool") or "")
    tool_input = tool_result.get("input") if isinstance(tool_result.get("input"), Mapping) else {}
    output = tool_result.get("output") if isinstance(tool_result.get("output"), Mapping) else {}
    path = str(output.get("path") or tool_input.get("path") or "")
    if not path:
        return {"success": False, "reason": "file result missing path"}

    if tool == "read_file":
        if "content" not in output:
            return {"success": False, "reason": "read_file result missing content"}
        return {"success": True, "reason": "read_file content available"}

    if tool == "write_file":
        content = tool_input.get("content")
        if not isinstance(content, str):
            return {"success": False, "reason": "write_file input missing content"}
        try:
            target = resolve_project_path(path)
        except Exception as exc:
            return {"success": False, "reason": f"write_file path invalid: {exc}"}
        if not target.is_file():
            return {"success": False, "reason": "write_file target was not created"}
        actual = target.read_text(encoding="utf-8")
        if actual != content:
            return {"success": False, "reason": "write_file content mismatch"}
        expected_bytes = len(content.encode("utf-8"))
        if output.get("bytes") not in {None, expected_bytes}:
            return {"success": False, "reason": "write_file byte count mismatch"}
        return {"success": True, "reason": "write_file state verified"}

    return {"success": True, "reason": "no file state validation required"}


def validate_command_output(tool_result: Mapping[str, Any]) -> dict[str, Any]:
    if not tool_result.get("success"):
        return {"success": False, "reason": "command tool reported failure"}

    tool = str(tool_result.get("tool") or "")
    output = tool_result.get("output") if isinstance(tool_result.get("output"), Mapping) else {}

    if tool in {"run_command", "git_diff"}:
        if output.get("timed_out"):
            return {"success": False, "reason": f"{tool} timed out"}
        if tool == "git_diff" and "code" not in output:
            return {"success": True, "reason": "git_diff result available"}
        if int(output.get("code", 1)) != 0:
            return {"success": False, "reason": f"{tool} exited with code {output.get('code')}"}
        return {"success": True, "reason": f"{tool} exited successfully"}

    if tool == "git_commit":
        add_result = output.get("add") if isinstance(output.get("add"), Mapping) else {}
        commit_result = output.get("commit") if isinstance(output.get("commit"), Mapping) else {}
        if int(add_result.get("code", 1)) != 0:
            return {"success": False, "reason": "git add failed"}
        if int(commit_result.get("code", 1)) != 0:
            return {"success": False, "reason": "git commit failed"}
        return {"success": True, "reason": "git commit completed"}

    return {"success": True, "reason": "no command validation required"}


def validate_task_success(execution: ExecutionResult) -> VerificationResult:
    if not execution.steps:
        return VerificationResult(done=False, retry=False, reason="plan produced no steps")

    invalid_steps = [step for step in execution.steps if not step.validation.get("success")]
    if invalid_steps:
        failed = invalid_steps[0]
        return VerificationResult(
            done=False,
            retry=True,
            reason=f"step {failed.step.id} validation failed: {failed.validation.get('reason')}",
        )

    failed_steps = [step for step in execution.steps if not step.success]
    if failed_steps:
        failed = failed_steps[0]
        tool_name = failed.step.tool or "reason"
        return VerificationResult(
            done=False,
            retry=True,
            reason=f"step {failed.step.id} failed using {tool_name}",
        )

    tool_steps = [step for step in execution.steps if step.step.tool is not None]
    if not tool_steps:
        return VerificationResult(done=False, retry=False, reason="plan executed no tools")

    return VerificationResult(done=True, retry=False, reason="all planned tool steps verified")


__all__ = [
    "VerificationResult",
    "Verifier",
    "validate_command_output",
    "validate_file_state",
    "validate_task_success",
]
