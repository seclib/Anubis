"""Production sandbox runtime for isolated ANUBIS agent execution."""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import shlex
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback
    resource = None


class SandboxViolation(ValueError):
    """Raised when a tool attempts to escape the sandbox boundary."""


@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds: int = 2
    memory_mb: int = 256
    timeout_seconds: float = 5.0
    output_max_chars: int = 12000

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_seconds": self.cpu_seconds,
            "memory_mb": self.memory_mb,
            "timeout_seconds": self.timeout_seconds,
            "output_max_chars": self.output_max_chars,
        }


class ResourceLimiter:
    """Applies process-level resource limits inside sandbox workers."""

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self.limits = limits or ResourceLimits()

    def apply(self) -> None:
        if resource is None:
            return
        cpu = max(1, int(self.limits.cpu_seconds))
        memory_bytes = max(16, int(self.limits.memory_mb)) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))


@dataclass(frozen=True)
class SandboxContext:
    task_id: str
    sandbox_id: str
    workspace: Path
    limits: ResourceLimits

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "sandbox_id": self.sandbox_id,
            "workspace": str(self.workspace),
            "limits": self.limits.to_dict(),
        }


@dataclass(frozen=True)
class SandboxExecutionResult:
    tool: str
    success: bool
    output: Any = ""
    logs: tuple[str, ...] = ()
    code: int | None = None
    timed_out: bool = False
    sandbox_id: str | None = None
    workspace: str | None = None
    worker_pid: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "success": self.success,
            "output": self.output,
            "logs": list(self.logs),
            "code": self.code,
            "timed_out": self.timed_out,
            "sandbox_id": self.sandbox_id,
            "workspace": self.workspace,
            "worker_pid": self.worker_pid,
            "error": self.error,
        }


@dataclass(frozen=True)
class SandboxRuntimeConfig:
    root_dir: str | None = None
    cleanup_on_success: bool = False
    cleanup_on_failure: bool = False
    default_limits: ResourceLimits = field(default_factory=ResourceLimits)


class SandboxRuntime:
    """Creates isolated, ephemeral workspaces for task execution."""

    def __init__(self, config: SandboxRuntimeConfig | None = None) -> None:
        self.config = config or SandboxRuntimeConfig()
        root = self.config.root_dir or tempfile.mkdtemp(prefix="anubis-sandboxes-")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, task_id: str, limits: ResourceLimits | None = None) -> SandboxContext:
        if not task_id.strip():
            raise ValueError("task_id is required")
        workspace = Path(tempfile.mkdtemp(prefix=f"{_safe_id(task_id)}-", dir=self.root)).resolve()
        return SandboxContext(
            task_id=task_id,
            sandbox_id=workspace.name,
            workspace=workspace,
            limits=limits or self.config.default_limits,
        )

    def cleanup(self, context: SandboxContext) -> None:
        if self._inside_root(context.workspace):
            shutil.rmtree(context.workspace, ignore_errors=True)

    def resolve_path(self, context: SandboxContext, value: str | os.PathLike[str]) -> Path:
        raw = Path(value)
        if raw.is_absolute():
            raise SandboxViolation(f"absolute host paths are not allowed: {value}")
        candidate = (context.workspace / raw).resolve(strict=False)
        if not _is_relative_to(candidate, context.workspace):
            raise SandboxViolation(f"path escapes sandbox workspace: {value}")
        return candidate

    def _inside_root(self, path: Path) -> bool:
        return _is_relative_to(path.resolve(strict=False), self.root)


class IsolatedToolExecutor:
    """Executes every tool call in a separate killable sandbox worker process."""

    ALLOWED_TOOLS = frozenset({"read_file", "write_file", "search_codebase", "run_command", "git_diff", "git_commit"})

    def __init__(
        self,
        *,
        runtime: SandboxRuntime | None = None,
        limits: ResourceLimits | None = None,
    ) -> None:
        self.runtime = runtime or SandboxRuntime()
        self.limits = limits

    def execute(
        self,
        *,
        task_id: str,
        tool: str,
        tool_input: dict[str, Any] | None = None,
        context: SandboxContext | None = None,
    ) -> SandboxExecutionResult:
        if tool not in self.ALLOWED_TOOLS:
            return SandboxExecutionResult(tool=tool, success=False, output="", error=f"tool not allowed in sandbox: {tool}")

        owns_context = context is None
        context = context or self.runtime.create(task_id, self.limits)
        queue: multiprocessing.Queue[dict[str, Any]] = multiprocessing.Queue(maxsize=1)
        process = multiprocessing.Process(
            target=_tool_worker,
            args=(context.to_dict(), tool, dict(tool_input or {}), queue),
            daemon=True,
        )
        process.start()
        process.join(context.limits.timeout_seconds)
        if process.is_alive():
            _kill_process(process)
            result = SandboxExecutionResult(
                tool=tool,
                success=False,
                output="",
                logs=("sandbox timeout enforced",),
                timed_out=True,
                sandbox_id=context.sandbox_id,
                workspace=str(context.workspace),
                worker_pid=process.pid,
                error="sandbox execution timed out",
            )
        else:
            try:
                payload = queue.get_nowait()
            except Empty:
                payload = {
                    "tool": tool,
                    "success": False,
                    "output": "",
                    "logs": ["sandbox worker exited without result"],
                    "code": process.exitcode,
                    "error": "sandbox worker exited without result",
                }
            result = SandboxExecutionResult(
                tool=tool,
                success=bool(payload.get("success")),
                output=payload.get("output", ""),
                logs=tuple(str(item) for item in payload.get("logs", ())),
                code=payload.get("code", process.exitcode),
                timed_out=bool(payload.get("timed_out", False)),
                sandbox_id=context.sandbox_id,
                workspace=str(context.workspace),
                worker_pid=payload.get("worker_pid", process.pid),
                error=payload.get("error"),
            )

        if owns_context and ((result.success and self.runtime.config.cleanup_on_success) or (not result.success and self.runtime.config.cleanup_on_failure)):
            self.runtime.cleanup(context)
        return result


class SandboxedToolIntegrationLayer:
    """ToolIntegrationLayer-compatible adapter backed by the sandbox executor."""

    def __init__(self, executor: IsolatedToolExecutor | None = None, *, task_id: str = "sandboxed-task") -> None:
        self.executor = executor or IsolatedToolExecutor()
        self.task_id = task_id

    def execute(self, tool: str, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
        task_id = str((tool_input or {}).get("task_id") or self.task_id)
        return self.executor.execute(task_id=task_id, tool=tool, tool_input=dict(tool_input or {})).to_dict()


class SandboxedExecutorAgent:
    """ExecutorAgent-compatible facade that forces all tools through the sandbox."""

    def __init__(self, *, executor: IsolatedToolExecutor | None = None, task_id: str = "sandboxed-task") -> None:
        from anubis.distributed.executor_agent import ExecutorAgent

        self.tools = SandboxedToolIntegrationLayer(executor, task_id=task_id)
        self.agent = ExecutorAgent(tools=self.tools)

    def execute(self, step: Any) -> Any:
        return self.agent.execute(step)

    def execute_dict(self, step: Any) -> dict[str, Any]:
        return self.agent.execute_dict(step)


def _tool_worker(context_payload: dict[str, Any], tool: str, tool_input: dict[str, Any], queue: multiprocessing.Queue) -> None:
    context = SandboxContext(
        task_id=context_payload["task_id"],
        sandbox_id=context_payload["sandbox_id"],
        workspace=Path(context_payload["workspace"]).resolve(),
        limits=ResourceLimits(**context_payload["limits"]),
    )
    ResourceLimiter(context.limits).apply()
    started = time.monotonic()
    timed_out = False
    try:
        output, code = _execute_tool(context, tool, tool_input)
        success = code == 0
        error = None if success else _stringify(output)
    except subprocess.TimeoutExpired as exc:
        output = f"command timed out after {exc.timeout} seconds"
        code = 124
        success = False
        timed_out = True
        error = output
    except Exception as exc:
        output = str(exc)
        code = 1
        success = False
        error = f"{exc.__class__.__name__}: {exc}"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    queue.put(
        {
            "tool": tool,
            "success": success,
            "output": _truncate(output, context.limits.output_max_chars),
            "logs": [
                f"sandbox_id={context.sandbox_id}",
                f"workspace={context.workspace}",
                f"worker_pid={os.getpid()}",
                f"duration_ms={elapsed_ms}",
            ],
            "code": code,
            "timed_out": timed_out,
            "worker_pid": os.getpid(),
            "error": error,
        }
    )


def _execute_tool(context: SandboxContext, tool: str, tool_input: dict[str, Any]) -> tuple[Any, int]:
    if tool == "read_file":
        path = _resolve(context, tool_input.get("path", ""))
        return path.read_text(encoding="utf-8"), 0
    if tool == "write_file":
        path = _resolve(context, tool_input.get("path", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(tool_input.get("content", "")), encoding="utf-8")
        return {"path": str(path), "bytes": path.stat().st_size}, 0
    if tool == "search_codebase":
        query = str(tool_input.get("query", ""))
        matches = _search(context.workspace, query)
        return {"query": query, "matches": matches}, 0
    if tool == "run_command":
        return _run_command(context, str(tool_input.get("cmd", "")))
    if tool == "git_diff":
        return _run_command(context, "git diff")
    if tool == "git_commit":
        message = str(tool_input.get("message", "sandbox commit"))
        return _run_command(context, f"git commit -m {shlex.quote(message)}")
    raise SandboxViolation(f"tool not allowed in sandbox: {tool}")


def _run_command(context: SandboxContext, command: str) -> tuple[str, int]:
    if not command.strip():
        raise SandboxViolation("command is required")
    tokens = shlex.split(command, posix=True)
    if not tokens:
        raise SandboxViolation("command is required")
    _reject_shell_surface(command)
    completed = subprocess.run(
        tokens,
        cwd=context.workspace,
        shell=False,
        text=True,
        capture_output=True,
        timeout=context.limits.timeout_seconds,
        start_new_session=True,
        env=_sandbox_env(context),
    )
    output = completed.stdout
    if completed.stderr:
        output = f"{output}{completed.stderr}"
    return output, completed.returncode


def _search(root: Path, query: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not query:
        return matches
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                matches.append({"path": relative, "line": line_no, "text": line})
    return matches


def _resolve(context: SandboxContext, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SandboxViolation("sandbox path is required")
    raw = Path(value)
    if raw.is_absolute():
        raise SandboxViolation(f"absolute host paths are not allowed: {value}")
    path = (context.workspace / raw).resolve(strict=False)
    if not _is_relative_to(path, context.workspace):
        raise SandboxViolation(f"path escapes sandbox workspace: {value}")
    return path


def _reject_shell_surface(command: str) -> None:
    for marker in (";", "&&", "||", "|", "`", "$(", "<(", ">(", "\n", "\r"):
        if marker in command:
            raise SandboxViolation(f"shell control or expansion is not allowed: {marker}")


def _sandbox_env(context: SandboxContext) -> dict[str, str]:
    return {
        "HOME": str(context.workspace),
        "TMPDIR": str(context.workspace),
        "PATH": os.environ.get("PATH", ""),
        "ANUBIS_SANDBOX_ID": context.sandbox_id,
    }


def _kill_process(process: multiprocessing.Process) -> None:
    if process.pid is None:
        process.terminate()
        process.join(1)
        return
    try:
        os.kill(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    process.join(0.5)
    if process.is_alive():
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.join(0.5)


def _truncate(value: Any, limit: int) -> Any:
    text = _stringify(value)
    return text[:limit]


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)[:48] or "task"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = [
    "IsolatedToolExecutor",
    "ResourceLimiter",
    "ResourceLimits",
    "SandboxContext",
    "SandboxExecutionResult",
    "SandboxRuntime",
    "SandboxRuntimeConfig",
    "SandboxViolation",
    "SandboxedExecutorAgent",
    "SandboxedToolIntegrationLayer",
]
