from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import os
import shlex
import subprocess
from typing import Any

from backend.core.config import settings
from backend.core.paths import ensure_inside


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
DANGEROUS_FLAG_PAIRS = {
    ("git", "--exec-path"),
    ("git", "config --global"),
    ("git", "config --system"),
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


@dataclass(frozen=True)
class ToolRequest:
    command: str
    justification: str
    cwd: str = "."
    allow_network: bool = False


@dataclass(frozen=True)
class ValidatedCommand:
    tokens: list[str]
    cwd: Path
    command: str


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    command: str
    code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class ToolValidationError(ValueError):
    pass


def _command_name(token: str) -> str:
    return Path(token).name.lower()


def _contains_shell_surface(command: str) -> str | None:
    for marker in SHELL_CONTROL + SHELL_EXPANSION:
        if marker in command:
            return marker
    return None


def _is_env_assignment(token: str) -> bool:
    if "=" not in token or token.startswith(("=", "-", "/", "./", "../", "~")):
        return False
    name, _ = token.split("=", 1)
    return bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()


def _looks_like_path(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token.startswith(("~", "/", "./", "../")):
        return True
    return "/" in token or "\\" in token


def _strip_redirection_prefix(token: str) -> str:
    value = token
    for prefix in (">>", "2>", "1>", "<", ">"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


class ToolValidator:
    def __init__(
        self,
        root: Path | None = None,
        allowed_commands: set[str] | None = None,
        max_command_chars: int = 4000,
    ) -> None:
        self.root = (root or settings.project_root).resolve()
        self.allowed_commands = allowed_commands or {command.lower() for command in settings.allowed_commands}
        self.max_command_chars = max_command_chars

    def validate(self, request: ToolRequest) -> ValidatedCommand:
        if not request.justification.strip():
            raise ToolValidationError("tool execution requires justification")
        if not request.command.strip():
            raise ToolValidationError("command is empty")
        if len(request.command) > self.max_command_chars:
            raise ToolValidationError("command is too long")

        marker = _contains_shell_surface(request.command)
        if marker:
            raise ToolValidationError(f"shell control or expansion is not allowed: {marker}")

        try:
            tokens = shlex.split(request.command, posix=True)
        except ValueError as exc:
            raise ToolValidationError(f"invalid command syntax: {exc}") from exc
        if not tokens:
            raise ToolValidationError("command is empty")
        if any(token in REDIRECTION for token in tokens):
            raise ToolValidationError("shell redirection is not allowed")

        cwd = ensure_inside(self.root, Path(request.cwd))
        command_index = self._command_index(tokens)
        command = _command_name(tokens[command_index])

        if command not in self.allowed_commands:
            raise ToolValidationError(f"command not whitelisted: {command}")
        if command in FORBIDDEN_COMMANDS:
            raise ToolValidationError(f"forbidden command: {command}")
        if command in NETWORK_COMMANDS and not request.allow_network:
            raise ToolValidationError(f"network command requires explicit allow_network: {command}")
        self._reject_inline_execution(command, tokens[command_index + 1 :])
        self._reject_dangerous_flags(command, tokens[command_index + 1 :])
        self._validate_paths(tokens, cwd)

        return ValidatedCommand(tokens=tokens, cwd=cwd, command=command)

    def _command_index(self, tokens: list[str]) -> int:
        for index, token in enumerate(tokens):
            if _is_env_assignment(token):
                continue
            return index
        raise ToolValidationError("command is missing")

    def _reject_inline_execution(self, command: str, args: list[str]) -> None:
        blocked = INLINE_EXEC_FLAGS.get(command, set())
        if blocked and any(arg in blocked for arg in args[:2]):
            raise ToolValidationError(f"inline execution is not allowed for {command}")

    def _reject_dangerous_flags(self, command: str, args: list[str]) -> None:
        joined = " ".join(args)
        for blocked_command, blocked_flag in DANGEROUS_FLAG_PAIRS:
            if command == blocked_command and blocked_flag in joined:
                raise ToolValidationError(f"dangerous option is not allowed: {blocked_flag}")

    def _validate_paths(self, tokens: list[str], cwd: Path) -> None:
        for token in tokens:
            value = _strip_redirection_prefix(token)
            if not value or value in REDIRECTION or value.startswith("-") or _is_env_assignment(value):
                if _is_env_assignment(value):
                    _, env_value = value.split("=", 1)
                    self._validate_path_value(env_value, cwd)
                continue
            self._validate_path_value(value, cwd)

    def _validate_path_value(self, value: str, cwd: Path) -> None:
        if not _looks_like_path(value):
            return
        candidate = Path(value).expanduser()
        if candidate.is_absolute() and str(candidate.resolve(strict=False)) in HOST_ROOTS:
            raise ToolValidationError(f"host/system path is not allowed: {value}")
        base = self.root if candidate.is_absolute() else cwd
        ensure_inside(self.root, base / candidate if not candidate.is_absolute() else candidate)


class SandboxExecutor:
    def __init__(self, validator: ToolValidator | None = None, log_path: Path | None = None) -> None:
        self.validator = validator or ToolValidator()
        self.log_path = log_path or settings.tool_log_path

    def execute(self, request: ToolRequest) -> ToolResult:
        started = datetime.now(UTC)
        validation: ValidatedCommand | None = None
        try:
            validation = self.validator.validate(request)
            completed = subprocess.run(
                validation.tokens,
                cwd=validation.cwd,
                shell=False,
                text=True,
                capture_output=True,
                timeout=settings.tool_timeout_seconds,
                env=self._environment(request.allow_network),
            )
            result = ToolResult(
                ok=completed.returncode == 0,
                command=request.command,
                code=completed.returncode,
                stdout=completed.stdout[:12000],
                stderr=completed.stderr[:12000],
                duration_ms=self._duration_ms(started),
            )
        except subprocess.TimeoutExpired as exc:
            result = ToolResult(
                ok=False,
                command=request.command,
                code=124,
                stdout=self._decode_timeout_stream(exc.stdout),
                stderr=self._decode_timeout_stream(exc.stderr) or "command timed out",
                duration_ms=self._duration_ms(started),
                timed_out=True,
            )
        except Exception as exc:
            result = ToolResult(
                ok=False,
                command=request.command,
                code=126,
                stdout="",
                stderr=str(exc),
                duration_ms=self._duration_ms(started),
            )
        self._log(request, result, validation)
        return result

    def _environment(self, allow_network: bool) -> dict[str, str]:
        env = {
            "HOME": str(self.validator.root),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONNOUSERSITE": "1",
        }
        if not allow_network:
            env.update(
                {
                    "http_proxy": "",
                    "https_proxy": "",
                    "HTTP_PROXY": "",
                    "HTTPS_PROXY": "",
                    "NO_PROXY": "*",
                }
            )
        return env

    def _log(self, request: ToolRequest, result: ToolResult, validation: ValidatedCommand | None) -> None:
        path = self.log_path
        if not path.is_absolute():
            path = settings.project_root / path
        path = ensure_inside(settings.project_root, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        event: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "request": asdict(request),
            "validation": {
                "accepted": validation is not None,
                "tokens": validation.tokens if validation else [],
                "cwd": str(validation.cwd) if validation else "",
                "command": validation.command if validation else "",
            },
            "result": asdict(result),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _duration_ms(self, started: datetime) -> int:
        return int((datetime.now(UTC) - started).total_seconds() * 1000)

    def _decode_timeout_stream(self, value: bytes | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode(errors="replace")[:12000]
        return str(value)[:12000]


__all__ = [
    "SandboxExecutor",
    "ToolRequest",
    "ToolResult",
    "ToolValidationError",
    "ToolValidator",
    "ValidatedCommand",
]
