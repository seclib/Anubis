"""Autonomous Git safety helpers."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    GIT_TEMP_BRANCH_PREFIX,
    GIT_USE_TEMP_BRANCH,
    GIT_VALIDATION_COMMANDS,
    TOOL_COMMAND_TIMEOUT,
)
from tools.sandbox import relative_to_workspace, validate_command, workspace_root

logger = logging.getLogger(__name__)


class GitAutonomyError(RuntimeError):
    """Raised when autonomous Git cannot complete safely."""


def _run_git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(workspace_root()),
        capture_output=True,
        text=True,
        timeout=TOOL_COMMAND_TIMEOUT,
        check=False,
    )
    logger.info(
        "git_autonomy command=%s code=%s stdout=%s stderr=%s",
        "git " + " ".join(args),
        result.returncode,
        result.stdout[:1000],
        result.stderr[:1000],
    )
    if check and result.returncode != 0:
        raise GitAutonomyError(result.stderr.strip() or result.stdout.strip())
    return result


def _run_validation_command(command: str) -> dict[str, Any]:
    tokens = validate_command(command)
    result = subprocess.run(
        tokens,
        cwd=str(workspace_root()),
        shell=False,
        capture_output=True,
        text=True,
        timeout=TOOL_COMMAND_TIMEOUT,
        check=False,
    )
    logger.info(
        "git_autonomy validation command=%s code=%s stdout=%s stderr=%s",
        command,
        result.returncode,
        result.stdout[:1000],
        result.stderr[:1000],
    )
    return {
        "command": command,
        "code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.returncode == 0,
    }


def _history_path() -> Path:
    return workspace_root() / "state" / "autonomous_git_history.json"


def _load_history() -> list[dict[str, Any]]:
    path = _history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _append_history(entry: dict[str, Any]) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history()
    history.append(entry)
    path.write_text(json.dumps(history[-100:], indent=2, ensure_ascii=False, default=str))


def _current_branch() -> str:
    result = _run_git(["branch", "--show-current"])
    branch = result.stdout.strip()
    return branch or "HEAD"


def _short_sha(ref: str = "HEAD") -> str:
    result = _run_git(["rev-parse", "--short", ref])
    return result.stdout.strip()


def _full_sha(ref: str = "HEAD") -> str:
    result = _run_git(["rev-parse", ref])
    return result.stdout.strip()


def _sanitize_branch_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._/-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-/.")
    return normalized[:48] or "task"


def _status_lines() -> list[str]:
    result = _run_git(["status", "--short"])
    return [line for line in result.stdout.splitlines() if line.strip()]


def _changed_files() -> list[str]:
    return [line[3:].strip() for line in _status_lines() if len(line) > 3]


def _diff_stat() -> str:
    result = _run_git(["diff", "--stat"])
    staged = _run_git(["diff", "--cached", "--stat"])
    return "\n".join(part for part in [result.stdout.strip(), staged.stdout.strip()] if part)


def git_status() -> dict[str, Any]:
    """Return the current Git branch and porcelain status."""
    return {
        "branch": _current_branch(),
        "head": _short_sha(),
        "dirty": bool(_status_lines()),
        "changes": _status_lines(),
    }


def generate_commit_message(task: str = "", max_files: int = 8) -> str:
    """Generate a concise deterministic commit message from current changes."""
    files = _changed_files()
    if task.strip():
        base = task.strip().splitlines()[0]
        base = re.sub(r"\s+", " ", base)
        if len(base) > 72:
            base = base[:69].rstrip() + "..."
        subject = base[0].upper() + base[1:] if base else "Update project"
    elif files:
        subject = f"Update {', '.join(files[:2])}"
    else:
        subject = "Update project"

    details = files[:max_files]
    body_lines = [f"- {path}" for path in details]
    if len(files) > max_files:
        body_lines.append(f"- and {len(files) - max_files} more file(s)")

    if not body_lines:
        return subject
    return f"{subject}\n\nChanged files:\n" + "\n".join(body_lines)


def run_git_validations(commands: list[str] | None = None) -> dict[str, Any]:
    """Run configured validation commands before committing."""
    validation_commands = commands if commands is not None else GIT_VALIDATION_COMMANDS
    results = [_run_validation_command(command) for command in validation_commands]
    return {
        "success": all(result["success"] for result in results),
        "commands": results,
    }


def create_temporary_branch(task: str = "", prefix: str | None = None) -> dict[str, Any]:
    """Create and checkout a temporary branch for the autonomous run."""
    branch_prefix = (prefix or GIT_TEMP_BRANCH_PREFIX).strip().strip("/") or "anubis/auto"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"{branch_prefix}/{timestamp}-{_sanitize_branch_part(task)}"
    previous_branch = _current_branch()
    result = _run_git(["checkout", "-b", branch_name], check=True)
    return {
        "success": True,
        "branch": branch_name,
        "previous_branch": previous_branch,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def autonomous_git_commit(
    task: str = "",
    message: str | None = None,
    use_temp_branch: bool | None = None,
    validation_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Validate changes and create an autonomous commit only when safe."""
    status_before = git_status()
    if not status_before["dirty"]:
        return {
            "success": True,
            "status": "no_changes",
            "message": "No Git changes to commit.",
            "status_before": status_before,
        }

    branch_result = None
    if GIT_USE_TEMP_BRANCH if use_temp_branch is None else use_temp_branch:
        branch_result = create_temporary_branch(task)

    validations = run_git_validations(validation_commands)
    if not validations["success"]:
        result = {
            "success": False,
            "status": "validation_failed",
            "message": "Validation failed; commit aborted to avoid broken commit.",
            "validations": validations,
            "status_before": status_before,
            "branch": branch_result,
        }
        logger.warning("git_autonomy commit aborted: validation failed")
        return result

    commit_message = message.strip() if isinstance(message, str) and message.strip() else generate_commit_message(task)
    _run_git(["add", "-A", "--", "."], check=True)
    staged = _run_git(["diff", "--cached", "--name-only"])
    staged_files = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
    if not staged_files:
        return {
            "success": True,
            "status": "no_staged_changes",
            "message": "No staged changes after validation.",
            "validations": validations,
            "status_before": status_before,
            "branch": branch_result,
        }

    commit = _run_git(["commit", "-m", commit_message])
    if commit.returncode != 0:
        return {
            "success": False,
            "status": "commit_failed",
            "message": commit.stderr.strip() or commit.stdout.strip(),
            "validations": validations,
            "status_before": status_before,
            "branch": branch_result,
        }

    commit_sha = _full_sha()
    entry = {
        "commit": commit_sha,
        "short_commit": _short_sha(),
        "branch": _current_branch(),
        "previous_branch": branch_result.get("previous_branch") if branch_result else status_before["branch"],
        "message": commit_message,
        "task": task,
        "files": staged_files,
        "validations": validations,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": relative_to_workspace(workspace_root()),
    }
    _append_history(entry)
    return {
        "success": True,
        "status": "committed",
        "commit": commit_sha,
        "short_commit": entry["short_commit"],
        "message": commit_message,
        "files": staged_files,
        "validations": validations,
        "branch": branch_result,
        "diff_stat": _diff_stat(),
    }


def rollback_last_autonomous_commit(hard: bool = False) -> dict[str, Any]:
    """Rollback the most recent autonomous commit by revert or hard reset."""
    history = _load_history()
    if not history:
        return {
            "success": False,
            "status": "no_history",
            "message": "No autonomous commit history found.",
        }

    last_entry = history[-1]
    commit_sha = str(last_entry.get("commit", "")).strip()
    if not commit_sha:
        return {
            "success": False,
            "status": "invalid_history",
            "message": "Last history entry has no commit SHA.",
        }

    if hard:
        target = f"{commit_sha}^"
        result = _run_git(["reset", "--hard", target])
        status = "reset"
    else:
        result = _run_git(["revert", "--no-edit", commit_sha])
        status = "reverted"

    success = result.returncode == 0
    rollback_entry = {
        **last_entry,
        "rollback": {
            "status": status if success else "failed",
            "hard": hard,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    history[-1] = rollback_entry
    _history_path().write_text(json.dumps(history[-100:], indent=2, ensure_ascii=False, default=str))
    return {
        "success": success,
        "status": status if success else "rollback_failed",
        "commit": commit_sha,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


__all__ = [
    "GitAutonomyError",
    "autonomous_git_commit",
    "create_temporary_branch",
    "generate_commit_message",
    "git_status",
    "rollback_last_autonomous_commit",
    "run_git_validations",
]
