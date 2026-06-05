"""Workspace sandbox helpers for legacy runtime tools.

This module is a compatibility surface for the existing ``tools/*`` runtime.
It centralizes path checks, command validation, and audit logging without
changing the callers yet. The canonical ToolService can later wrap this module
as a legacy adapter.
"""

from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from config import (
        PROJECT_ROOT,
        TOOL_AUDIT_FILE,
        TOOL_COMMAND_MAX_LENGTH,
        TOOL_COMMAND_TIMEOUT,
        TOOL_OUTPUT_MAX_CHARS,
        WORKSPACE_ROOT,
    )
except Exception:  # pragma: no cover - fallback for isolated imports
    PROJECT_ROOT = Path.cwd()
    WORKSPACE_ROOT = PROJECT_ROOT
    TOOL_AUDIT_FILE = Path("state/tool_audit.log")
    TOOL_COMMAND_MAX_LENGTH = 4000
    TOOL_COMMAND_TIMEOUT = 120
    TOOL_OUTPUT_MAX_CHARS = 20000


class SandboxViolation(ValueError):
    """Raised when a tool request escapes the workspace sandbox."""


SHELL_CONTROL = (";", "&&", "||", "|", "\n", "\r")
SHELL_EXPANSION = ("`", "$(", "<(", ">(")
REDIRECTION = {">", ">>", "1>", "2>", "<", "<<", "<<<"}

FORBIDDEN_COMMANDS = {
    "apt",
    "apt-get",
    "chmod",
    "chown",
    "chroot",
    "dd",
    "docker",
    "kill",
    "mkfs",
    "mount",
    "mv",
    "pkill",
    "podman",
    "reboot",
    "rm",
    "rmdir",
    "service",
    "shutdown",
    "su",
    "sudo",
    "systemctl",
    "umount",
}
NETWORK_COMMANDS = {"curl", "ftp", "nc", "netcat", "scp", "sftp", "ssh", "telnet", "wget"}
ALLOWED_COMMANDS = {
    "cat",
    "echo",
    "find",
    "git",
    "grep",
    "head",
    "ls",
    "node",
    "npm",
    "python",
    "python3",
    "pytest",
    "pwd",
    "rg",
    "sed",
    "sleep",
    "tail",
    "unittest",
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
HOST_ROOTS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/home",
    "/lib",
    "/lib64",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/sys",
    "/tmp",
    "/usr",
    "/var",
}


def workspace_root() -> Path:
    return Path(WORKSPACE_ROOT).expanduser().resolve()


def resolve_workspace_path(path: str | os.PathLike[str], *, must_exist: bool = True) -> Path:
    root = workspace_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    _ensure_inside_workspace(resolved)
    if must_exist and not resolved.exists():
        raise FileNotFoundError(relative_to_workspace(resolved))
    return resolved


def relative_to_workspace(path: str | os.PathLike[str]) -> str:
    root = workspace_root()
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def validate_command(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise SandboxViolation("command is empty")
    if len(command) > int(TOOL_COMMAND_MAX_LENGTH):
        raise SandboxViolation("command is too long")

    marker = _shell_surface(command)
    if marker:
        raise SandboxViolation(f"shell control or expansion is not allowed: {marker}")

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise SandboxViolation(f"invalid command syntax: {exc}") from exc
    if not tokens:
        raise SandboxViolation("command is empty")
    if any(token in REDIRECTION for token in tokens):
        raise SandboxViolation("shell redirection is not allowed")

    command_index = _command_index(tokens)
    executable = Path(tokens[command_index]).name.lower()
    if executable in FORBIDDEN_COMMANDS:
        raise SandboxViolation(f"forbidden command: {executable}")
    if executable in NETWORK_COMMANDS:
        raise SandboxViolation(f"network command is disabled: {executable}")
    if executable not in ALLOWED_COMMANDS:
        raise SandboxViolation(f"command not whitelisted: {executable}")
    if any(flag in INLINE_EXEC_FLAGS.get(executable, set()) for flag in tokens[command_index + 1 : command_index + 3]):
        raise SandboxViolation(f"inline execution is not allowed for {executable}")

    for token in tokens:
        if _is_env_assignment(token):
            _, value = token.split("=", 1)
            _validate_path_token(value)
        else:
            _validate_path_token(token)
    return tokens


def secure_command_options() -> dict[str, Any]:
    return {
        "cwd": str(workspace_root()),
        "timeout": int(TOOL_COMMAND_TIMEOUT),
        "max_output_chars": int(TOOL_OUTPUT_MAX_CHARS),
    }


def audit_tool_action(
    action: str,
    tool: str,
    *,
    args: Mapping[str, Any] | None = None,
    success: bool | None = None,
    result: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    audit_path = resolve_workspace_path(TOOL_AUDIT_FILE, must_exist=False)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": time.time(),
        "action": action,
        "tool": tool,
        "args": dict(args or {}),
        "success": success,
        "result": dict(result or {}),
        "error": error,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _shell_surface(command: str) -> str | None:
    for marker in SHELL_CONTROL + SHELL_EXPANSION:
        if marker in command:
            return marker
    return None


def _command_index(tokens: list[str]) -> int:
    for index, token in enumerate(tokens):
        if not _is_env_assignment(token):
            return index
    raise SandboxViolation("command is missing")


def _is_env_assignment(token: str) -> bool:
    if "=" not in token or token.startswith(("=", "-", "/", "./", "../", "~")):
        return False
    name, _ = token.split("=", 1)
    return bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()


def _looks_like_path(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    return token.startswith(("~", "/", "./", "../")) or "/" in token or "\\" in token


def _validate_path_token(token: str) -> None:
    if not _looks_like_path(token):
        return
    candidate = Path(token).expanduser()
    if candidate.is_absolute() and str(candidate.resolve(strict=False)) in HOST_ROOTS:
        raise SandboxViolation(f"host/system path is not allowed: {token}")
    resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (workspace_root() / candidate).resolve(strict=False)
    _ensure_inside_workspace(resolved)


def _ensure_inside_workspace(path: Path) -> None:
    root = workspace_root()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SandboxViolation(f"path escapes workspace: {path}") from exc


__all__ = [
    "SandboxViolation",
    "audit_tool_action",
    "relative_to_workspace",
    "resolve_workspace_path",
    "secure_command_options",
    "validate_command",
    "workspace_root",
]
