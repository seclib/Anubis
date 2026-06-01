"""Workspace sandbox helpers for tool execution."""

from __future__ import annotations

import json
import logging
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.workspace import (
    WorkspaceViolation as SandboxViolation,
    ensure_inside_workspace,
    relative_to_workspace,
    resolve_workspace_path,
    workspace_root,
)
from config import (
    TOOL_AUDIT_FILE,
    TOOL_COMMAND_MAX_LENGTH,
    TOOL_COMMAND_TIMEOUT,
    TOOL_OUTPUT_MAX_CHARS,
)

logger = logging.getLogger(__name__)

FORBIDDEN_COMMANDS = {
    "apt",
    "apt-get",
    "chroot",
    "curl",
    "dd",
    "docker",
    "ftp",
    "iptables",
    "kubectl",
    "mount",
    "nc",
    "netcat",
    "nsenter",
    "podman",
    "rsync",
    "scp",
    "sftp",
    "ssh",
    "su",
    "sudo",
    "systemctl",
    "telnet",
    "umount",
    "unshare",
    "wget",
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

SHELL_EXPANSION_MARKERS = ("$(", "`", "<(", ">(")
SHELL_CONTROL_MARKERS = ("&&", "||", ";", "|", "&", "\n", "\r")
SHELL_REDIRECTION_OPERATORS = {"<<", "<<-", "<<<", ">|"}
HOST_ESCAPE_PATHS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/" + "home",
    "/lib",
    "/lib64",
    "/media",
    "/mnt",
    "/" + "opt",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/tmp",
    "/usr",
    "/var",
}


def _ensure_inside_workspace(path: Path, root: Path) -> None:
    ensure_inside_workspace(path, root)


def _compact(value: Any, limit: int = 1000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text[:limit]


def _audit_path() -> Path:
    configured = Path(TOOL_AUDIT_FILE).expanduser()
    root = workspace_root()
    candidate = configured if configured.is_absolute() else root / configured
    resolved = candidate.resolve(strict=False)
    _ensure_inside_workspace(resolved, root)
    return resolved


def audit_tool_action(
    action: str,
    tool: str,
    *,
    args: Mapping[str, Any] | None = None,
    success: bool | None = None,
    result: Any = None,
    error: Any = None,
) -> None:
    compact_args = _compact(dict(args or {}), limit=2000)
    compact_result = _compact(result, limit=4000)
    compact_error = _compact(error, limit=2000)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "tool": tool,
        "success": success,
        "args": compact_args,
        "result": compact_result,
        "error": compact_error,
    }
    logger.info(
        "tool_audit action=%s tool=%s success=%s",
        action, tool, success,
    )
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        logger.debug("Failed to write tool audit file", exc_info=True)


def _command_name(token: str) -> str:
    return Path(token).name.lower()


def _is_env_assignment(token: str) -> bool:
    if "=" not in token or token.startswith(("=", "./", "../", "/", "~")):
        return False
    name, _ = token.split("=", 1)
    return bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()


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


def _reject_host_escape_path(value: str) -> None:
    if not value.startswith("/"):
        return
    normalized = str(Path(value))
    if normalized in HOST_ESCAPE_PATHS:
        raise SandboxViolation(f"Host/system path is not allowed in sandbox command: {value}")


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
    _reject_host_escape_path(value)
    if _looks_like_path(value):
        resolve_workspace_path(value, must_exist=False)


def _validate_shell_surface(cmd: str) -> None:
    if len(cmd) > TOOL_COMMAND_MAX_LENGTH:
        raise SandboxViolation(
            f"Command is too long for sandbox: {len(cmd)} > {TOOL_COMMAND_MAX_LENGTH}"
        )
    for marker in SHELL_EXPANSION_MARKERS:
        if marker in cmd:
            raise SandboxViolation(f"Shell expansion is not allowed in sandbox: {marker}")
    for marker in SHELL_CONTROL_MARKERS:
        if marker in cmd:
            raise SandboxViolation(f"Shell control operator is not allowed in sandbox: {marker}")


def validate_command(cmd: str) -> list[str]:
    if not isinstance(cmd, str) or not cmd.strip():
        raise SandboxViolation("Command must be a non-empty string")
    _validate_shell_surface(cmd)

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise SandboxViolation(f"Invalid shell command: {exc}") from exc

    if not tokens:
        raise SandboxViolation("Command must not be empty")

    previous_command = True
    for index, token in enumerate(tokens):
        if token in SHELL_REDIRECTION_OPERATORS:
            raise SandboxViolation(f"Shell redirection operator is not allowed: {token}")

        command_name = _command_name(token)
        if previous_command:
            if _is_env_assignment(token):
                _validate_path_token(token)
                continue
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
        "max_output_chars": TOOL_OUTPUT_MAX_CHARS,
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
