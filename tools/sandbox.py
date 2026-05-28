"""Workspace sandbox helpers for tool execution."""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, Mapping

from config import TOOL_COMMAND_TIMEOUT, WORKSPACE_ROOT

logger = logging.getLogger(__name__)

FORBIDDEN_COMMANDS = {
    "chroot",
    "docker",
    "kubectl",
    "mount",
    "nsenter",
    "podman",
    "rsync",
    "scp",
    "sftp",
    "ssh",
    "su",
    "sudo",
    "systemctl",
    "umount",
    "unshare",
}

INLINE_EXEC_FLAGS = {
    "bash": {"-c", "-lc"},
    "dash": {"-c"},
    "node": {"-e", "--eval"},
    "perl": {"-e"},
    "php": {"-r"},
    "python": {"-c"},
    "python3": {"-c"},
    "ruby": {"-e"},
    "sh": {"-c"},
}


class SandboxViolation(PermissionError):
    """Raised when a tool attempts to leave the workspace sandbox."""


def workspace_root() -> Path:
    root = Path(WORKSPACE_ROOT).expanduser().resolve()
    if not root.exists():
        raise SandboxViolation(f"Workspace root does not exist: {root}")
    if not root.is_dir():
        raise SandboxViolation(f"Workspace root is not a directory: {root}")
    return root


def _ensure_inside_workspace(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SandboxViolation(f"Path escapes workspace: {path}") from exc


def resolve_workspace_path(path: str | Path = ".", *, must_exist: bool = False) -> Path:
    if path is None:
        path = "."

    raw_path = str(path)
    if "\x00" in raw_path:
        raise SandboxViolation("Path contains a null byte")

    root = workspace_root()
    requested_path = Path(raw_path).expanduser()
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    resolved = candidate.resolve(strict=False)
    _ensure_inside_workspace(resolved, root)

    if must_exist and not resolved.exists():
        raise SandboxViolation(f"Path does not exist in workspace: {raw_path}")

    return resolved


def relative_to_workspace(path: str | Path) -> str:
    root = workspace_root()
    resolved = resolve_workspace_path(path, must_exist=False)
    return "." if resolved == root else str(resolved.relative_to(root))


def _compact(value: Any, limit: int = 1000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text[:limit]


def audit_tool_action(
    action: str,
    tool: str,
    *,
    args: Mapping[str, Any] | None = None,
    success: bool | None = None,
    result: Any = None,
    error: Any = None,
) -> None:
    logger.info(
        "tool_audit action=%s tool=%s success=%s args=%s result=%s error=%s",
        action,
        tool,
        success,
        _compact(dict(args or {})),
        _compact(result),
        _compact(error),
    )


def _command_name(token: str) -> str:
    return Path(token).name.lower()


def _looks_like_path(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    value = token
    for prefix in (">>", "2>", "1>", "<", ">"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if not value:
        return False
    if value.startswith(("~", "/", "./", "../")):
        return True
    return "/" in value or "\\" in value


def _validate_path_token(token: str) -> None:
    value = token.strip()
    for prefix in (">>", "2>", "1>", "<", ">"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if not value or value.startswith("-"):
        return
    if "=" in value and not value.startswith(("./", "../", "/", "~")):
        maybe_path = value.split("=", 1)[1]
        if maybe_path:
            value = maybe_path
    if _looks_like_path(value):
        resolve_workspace_path(value, must_exist=False)


def validate_command(cmd: str) -> list[str]:
    if not isinstance(cmd, str) or not cmd.strip():
        raise SandboxViolation("Command must be a non-empty string")

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise SandboxViolation(f"Invalid shell command: {exc}") from exc

    if not tokens:
        raise SandboxViolation("Command must not be empty")

    previous_command = True
    for index, token in enumerate(tokens):
        if token in {";", "&&", "||", "|"}:
            previous_command = True
            continue

        command_name = _command_name(token)
        if previous_command:
            if command_name in FORBIDDEN_COMMANDS:
                raise SandboxViolation(f"Command is not allowed in sandbox: {command_name}")
            flags = INLINE_EXEC_FLAGS.get(command_name)
            if flags and any(flag in tokens[index + 1 : index + 3] for flag in flags):
                raise SandboxViolation(f"Inline execution is not allowed in sandbox: {command_name}")
            previous_command = False

        _validate_path_token(token)

    return tokens


def secure_command_options() -> dict[str, Any]:
    root = workspace_root()
    return {
        "cwd": str(root),
        "timeout": TOOL_COMMAND_TIMEOUT,
    }


__all__ = [
    "SandboxViolation",
    "audit_tool_action",
    "relative_to_workspace",
    "resolve_workspace_path",
    "secure_command_options",
    "validate_command",
    "workspace_root",
]
