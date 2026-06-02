from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json
import re
import uuid
from typing import Any, Callable, Literal, Mapping


SANDBOX_ARCHITECTURE = """
Skill Runtime
  -> Validation Layer
  -> Policy Engine
  -> Sandbox Executor
  -> Isolated Tool Execution
  -> Logger + Audit Trail
"""

ToolName = Literal["file_read", "file_write", "memory_search", "obsidian_read", "llm_call", "predefined_tool"]
Decision = Literal["allow", "deny"]

DEFAULT_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "file_read",
        "file_write",
        "memory_search",
        "obsidian_read",
        "llm_call",
        "predefined_tool",
    }
)
FORBIDDEN_KEYS = {"command", "shell", "python", "code", "eval", "exec", "subprocess", "socket", "requests"}
FORBIDDEN_TEXT = re.compile(
    r"(?i)(rm\s+-rf|sudo|curl\s+|wget\s+|bash\s+-c|sh\s+-c|python\s+-c|eval\(|exec\(|__import__|subprocess|socket|/etc/|/proc/|~\/)"
)


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_tools: frozenset[str] = DEFAULT_ALLOWED_TOOLS
    allowed_roots: tuple[Path, ...] = (Path("vault"), Path("state/skill-sandbox"))
    obsidian_root: Path = Path("vault")
    network_allowed: bool = False
    timeout_seconds: float = 10.0
    max_input_bytes: int = 64_000
    max_output_bytes: int = 128_000


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    step_id: str = ""
    skill_name: str = ""


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    sanitized_args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    tool: str
    step_id: str
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    audit_id: str = ""


class SandboxViolation(RuntimeError):
    pass


class AuditLogger:
    def __init__(self, path: Path = Path("state/skill_sandbox_audit.jsonl")) -> None:
        self.path = path

    def log(self, event: Mapping[str, Any]) -> str:
        audit_id = str(event.get("audit_id") or uuid.uuid4())
        payload = {
            "audit_id": audit_id,
            "timestamp": datetime.now(UTC).isoformat(),
            **dict(event),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True) + "\n")
        return audit_id


class Whitelist:
    def __init__(self, tools: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self._tools = dict(tools or {})

    def register(self, name: str, func: Callable[..., Any]) -> None:
        if name not in DEFAULT_ALLOWED_TOOLS:
            raise SandboxViolation(f"tool cannot be registered: {name}")
        self._tools[name] = func

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise SandboxViolation(f"tool is not registered: {name}")
        return self._tools[name]

    def names(self) -> set[str]:
        return set(self._tools)


class PolicyEngine:
    def __init__(self, policy: SandboxPolicy) -> None:
        self.policy = policy
        self.allowed_roots = tuple(root.resolve(strict=False) for root in policy.allowed_roots)
        self.obsidian_root = policy.obsidian_root.resolve(strict=False)

    def evaluate(self, call: ToolCall) -> PolicyResult:
        if call.tool not in self.policy.allowed_tools:
            return PolicyResult("deny", f"tool not allowed: {call.tool}")
        if call.tool in {"shell", "command", "run_command"}:
            return PolicyResult("deny", "raw shell execution is forbidden")
        if encoded_size(call.args) > self.policy.max_input_bytes:
            return PolicyResult("deny", "input too large")
        if self._contains_forbidden_surface(call.args):
            return PolicyResult("deny", "forbidden execution surface detected")
        try:
            args = self._sanitize_args(call.tool, call.args)
        except SandboxViolation as exc:
            return PolicyResult("deny", str(exc))
        return PolicyResult("allow", "allowed", args)

    def _sanitize_args(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        clean = json.loads(json.dumps(args, default=str))
        if tool in {"file_read", "file_write"}:
            clean["path"] = str(self._safe_path(str(clean.get("path", "")), read_only=False))
        if tool == "obsidian_read":
            clean["path"] = str(self._safe_obsidian_path(str(clean.get("path", ""))))
        if tool == "llm_call":
            clean["network_allowed"] = self.policy.network_allowed
        if tool == "predefined_tool":
            name = str(clean.get("name", ""))
            if name not in self.policy.allowed_tools or name == "predefined_tool":
                raise SandboxViolation(f"nested tool not allowed: {name}")
        return clean

    def _safe_path(self, value: str, *, read_only: bool) -> Path:
        if not value:
            raise SandboxViolation("path is required")
        path = Path(value).expanduser()
        resolved = path.resolve(strict=False) if path.is_absolute() else path.resolve(strict=False)
        if not any(is_relative_to(resolved, root) for root in self.allowed_roots):
            raise SandboxViolation("path outside allowed roots")
        if read_only and not resolved.exists():
            raise SandboxViolation("read path does not exist")
        return resolved

    def _safe_obsidian_path(self, value: str) -> Path:
        if not value:
            raise SandboxViolation("obsidian path is required")
        resolved = (self.obsidian_root / value).resolve(strict=False)
        if not is_relative_to(resolved, self.obsidian_root):
            raise SandboxViolation("obsidian path outside vault")
        return resolved

    def _contains_forbidden_surface(self, value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_KEYS:
                    return True
                if self._contains_forbidden_surface(item):
                    return True
        elif isinstance(value, list):
            return any(self._contains_forbidden_surface(item) for item in value)
        elif isinstance(value, str):
            return bool(FORBIDDEN_TEXT.search(value))
        return False


class SafeToolWrapper:
    def __init__(self, tools: Whitelist, policy: SandboxPolicy) -> None:
        self.tools = tools
        self.policy = policy

    def execute(self, call: ToolCall, args: dict[str, Any]) -> Any:
        tool = self.tools.get(call.tool)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(tool, **args)
            return future.result(timeout=self.policy.timeout_seconds)


class ZeroTrustSandboxExecutor:
    def __init__(
        self,
        *,
        policy: SandboxPolicy | None = None,
        whitelist: Whitelist | None = None,
        audit: AuditLogger | None = None,
    ) -> None:
        self.policy = policy or SandboxPolicy()
        self.whitelist = whitelist or Whitelist(default_tools())
        self.engine = PolicyEngine(self.policy)
        self.wrapper = SafeToolWrapper(self.whitelist, self.policy)
        self.audit = audit or AuditLogger()

    def execute(self, call: ToolCall) -> SandboxResult:
        started = datetime.now(UTC)
        audit_id = str(uuid.uuid4())
        decision = self.engine.evaluate(call)
        base_event = {"audit_id": audit_id, "skill": call.skill_name, "step_id": call.step_id, "tool": call.tool}
        if decision.decision != "allow":
            result = SandboxResult(False, call.tool, call.step_id, error=decision.reason, audit_id=audit_id)
            self.audit.log({**base_event, "decision": asdict(decision), "result": asdict(result)})
            return result
        try:
            output = self.wrapper.execute(call, decision.sanitized_args)
            output = truncate_output(output, self.policy.max_output_bytes)
            result = SandboxResult(True, call.tool, call.step_id, output=output, duration_ms=elapsed_ms(started), audit_id=audit_id)
        except FutureTimeout:
            result = SandboxResult(False, call.tool, call.step_id, error="operation timed out", duration_ms=elapsed_ms(started), audit_id=audit_id)
        except Exception as exc:
            result = SandboxResult(False, call.tool, call.step_id, error=str(exc), duration_ms=elapsed_ms(started), audit_id=audit_id)
        self.audit.log({**base_event, "decision": asdict(decision), "result": asdict(result)})
        return result


def default_tools() -> dict[str, Callable[..., Any]]:
    return {
        "file_read": lambda path: Path(path).read_text(encoding="utf-8")[:128_000],
        "file_write": safe_write,
        "obsidian_read": lambda path: Path(path).read_text(encoding="utf-8")[:128_000],
        "memory_search": lambda query, **_: [],
        "llm_call": lambda prompt, **_: "",
    }


def safe_write(path: str, content: str, **_: Any) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")
    return {"path": str(target), "bytes": len(str(content).encode("utf-8"))}


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def encoded_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def truncate_output(value: Any, max_bytes: int) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return value
    return {"truncated": True, "preview": encoded[:max_bytes]}


def elapsed_ms(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


__all__ = [
    "AuditLogger",
    "PolicyEngine",
    "PolicyResult",
    "SANDBOX_ARCHITECTURE",
    "SandboxPolicy",
    "SandboxResult",
    "SandboxViolation",
    "SafeToolWrapper",
    "ToolCall",
    "Whitelist",
    "ZeroTrustSandboxExecutor",
]
