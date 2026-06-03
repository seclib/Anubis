from __future__ import annotations

import subprocess
from typing import Any, Mapping

from backend.core.config import settings
from backend.tools.base import BaseTool, require_string


def _run_git(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", *args],
        cwd=settings.project_root.resolve(),
        capture_output=True,
        text=True,
        timeout=settings.tool_timeout_seconds,
        check=False,
    )
    return {
        "code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


class GitDiffTool(BaseTool):
    name = "git_diff"

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        return _run_git(["diff"])

    def succeeded(self, output: Any) -> bool:
        return isinstance(output, dict) and output.get("code") == 0


class GitCommitTool(BaseTool):
    name = "git_commit"

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        message = require_string(tool_input, "message").strip()
        if not message:
            raise ValueError("message must not be empty")

        add_result = _run_git(["add", "-A"])
        if add_result["code"] != 0:
            return {"add": add_result, "commit": None}

        commit_result = _run_git(["commit", "-m", message])
        return {
            "add": add_result,
            "commit": commit_result,
        }

    def succeeded(self, output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        add_result = output.get("add")
        commit_result = output.get("commit")
        return (
            isinstance(add_result, dict)
            and add_result.get("code") == 0
            and isinstance(commit_result, dict)
            and commit_result.get("code") == 0
        )


def git_diff() -> dict[str, Any]:
    return GitDiffTool().invoke({})


def git_commit(message: str) -> dict[str, Any]:
    return GitCommitTool().invoke({"message": message})


__all__ = ["GitCommitTool", "GitDiffTool", "git_commit", "git_diff"]
