"""Strict filesystem jail for ANUBIS sandboxed agent file access."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class FilesystemJailViolation(PermissionError):
    """Raised when an agent attempts unauthorized filesystem access."""


class FileAccessAction(StrEnum):
    READ = "read"
    WRITE = "write"


class FileAccessDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


SYSTEM_DIRECTORIES = frozenset(
    {
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/home",
        "/lib",
        "/lib64",
        "/media",
        "/mnt",
        "/opt",
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
)


@dataclass(frozen=True)
class VirtualWorkspace:
    task_id: str
    virtual_root: str
    real_root: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "virtual_root": self.virtual_root,
            "real_root": str(self.real_root),
        }


@dataclass(frozen=True)
class PathValidationResult:
    task_id: str
    requested_path: str
    real_path: Path | None
    allowed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requested_path": self.requested_path,
            "real_path": str(self.real_path) if self.real_path else None,
            "allowed": self.allowed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FileAccessAuditEntry:
    task_id: str
    action: FileAccessAction
    requested_path: str
    decision: FileAccessDecision
    reason: str | None = None
    real_path: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action.value,
            "requested_path": self.requested_path,
            "decision": self.decision.value,
            "reason": self.reason,
            "real_path": self.real_path,
            "created_at": self.created_at.isoformat(),
        }


class FileAccessAuditor:
    """Records every filesystem read/write attempt."""

    def __init__(self, audit_log_path: str | Path | None = None) -> None:
        self.audit_log_path = Path(audit_log_path).resolve() if audit_log_path else None
        self._entries: list[FileAccessAuditEntry] = []

    def record(self, entry: FileAccessAuditEntry) -> FileAccessAuditEntry:
        self._entries.append(entry)
        if self.audit_log_path is not None:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
        return entry

    def entries(self) -> tuple[FileAccessAuditEntry, ...]:
        return tuple(self._entries)


@dataclass(frozen=True)
class FilesystemJailConfig:
    root_dir: str | None = None
    audit_log_path: str | None = None
    virtual_prefix: str = "/workspace"


class PathValidator:
    """Validates virtual workspace paths against a single task root."""

    def __init__(self, *, virtual_prefix: str = "/workspace") -> None:
        self.virtual_prefix = "/" + virtual_prefix.strip("/")

    def validate(self, workspace: VirtualWorkspace, requested_path: str) -> PathValidationResult:
        try:
            real_path = self._validate_or_raise(workspace, requested_path)
            return PathValidationResult(workspace.task_id, requested_path, real_path, True)
        except FilesystemJailViolation as exc:
            return PathValidationResult(workspace.task_id, requested_path, None, False, str(exc))

    def enforce(self, workspace: VirtualWorkspace, requested_path: str) -> Path:
        result = self.validate(workspace, requested_path)
        if not result.allowed or result.real_path is None:
            raise FilesystemJailViolation(result.reason or "filesystem access denied")
        return result.real_path

    def _validate_or_raise(self, workspace: VirtualWorkspace, requested_path: str) -> Path:
        if not isinstance(requested_path, str) or not requested_path.strip():
            raise FilesystemJailViolation("path must be a non-empty virtual workspace path")
        if any(requested_path == system_dir or requested_path.startswith(f"{system_dir}/") for system_dir in SYSTEM_DIRECTORIES):
            if not requested_path.startswith(f"{workspace.virtual_root}/"):
                raise FilesystemJailViolation(f"system directory access denied: {requested_path}")
        if not requested_path.startswith("/"):
            raise FilesystemJailViolation("relative paths are denied; use /workspace/<task_id>/...")
        if not requested_path.startswith(f"{workspace.virtual_root}/"):
            raise FilesystemJailViolation(f"path is outside assigned workspace: {requested_path}")

        relative = requested_path[len(workspace.virtual_root) + 1 :]
        raw_parts = relative.split("/")
        if any(part in {"..", ""} for part in raw_parts):
            raise FilesystemJailViolation("path traversal is denied")
        parts = Path(relative).parts
        if not parts:
            raise FilesystemJailViolation("workspace root file access requires a child path")

        candidate = (workspace.real_root / relative).resolve(strict=False)
        if not _is_relative_to(candidate, workspace.real_root):
            raise FilesystemJailViolation(f"path escapes assigned workspace: {requested_path}")
        return candidate


class FilesystemJail:
    """Deny-by-default filesystem access control for agent tasks."""

    def __init__(
        self,
        config: FilesystemJailConfig | None = None,
        *,
        auditor: FileAccessAuditor | None = None,
        validator: PathValidator | None = None,
    ) -> None:
        self.config = config or FilesystemJailConfig()
        root = self.config.root_dir or tempfile.mkdtemp(prefix="anubis-fs-jail-")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        audit_path = self.config.audit_log_path
        if audit_path is None:
            audit_path = str(self.root / "_audit" / "filesystem.jsonl")
        self.auditor = auditor or FileAccessAuditor(audit_path)
        self.validator = validator or PathValidator(virtual_prefix=self.config.virtual_prefix)
        self._workspaces: dict[str, VirtualWorkspace] = {}

    def create_workspace(self, task_id: str) -> VirtualWorkspace:
        safe_task = _safe_task_id(task_id)
        real_root = (self.root / safe_task).resolve(strict=False)
        real_root.mkdir(parents=True, exist_ok=True)
        workspace = VirtualWorkspace(
            task_id=safe_task,
            virtual_root=f"{self.validator.virtual_prefix}/{safe_task}",
            real_root=real_root,
        )
        self._workspaces[safe_task] = workspace
        return workspace

    def workspace_for(self, task_id: str) -> VirtualWorkspace:
        safe_task = _safe_task_id(task_id)
        return self._workspaces.get(safe_task) or self.create_workspace(safe_task)

    def validate_path(self, task_id: str, requested_path: str) -> PathValidationResult:
        return self.validator.validate(self.workspace_for(task_id), requested_path)

    def read_file(self, task_id: str, requested_path: str) -> str:
        real_path = self._authorize(task_id, FileAccessAction.READ, requested_path)
        return real_path.read_text(encoding="utf-8")

    def write_file(self, task_id: str, requested_path: str, content: str) -> Path:
        real_path = self._authorize(task_id, FileAccessAction.WRITE, requested_path)
        real_path.parent.mkdir(parents=True, exist_ok=True)
        real_path.write_text(content, encoding="utf-8")
        return real_path

    def audit_entries(self) -> tuple[FileAccessAuditEntry, ...]:
        return self.auditor.entries()

    def _authorize(self, task_id: str, action: FileAccessAction, requested_path: str) -> Path:
        workspace = self.workspace_for(task_id)
        result = self.validator.validate(workspace, requested_path)
        decision = FileAccessDecision.ALLOW if result.allowed else FileAccessDecision.DENY
        self.auditor.record(
            FileAccessAuditEntry(
                task_id=workspace.task_id,
                action=action,
                requested_path=requested_path,
                decision=decision,
                reason=result.reason,
                real_path=str(result.real_path) if result.real_path else None,
            )
        )
        if not result.allowed or result.real_path is None:
            raise FilesystemJailViolation(result.reason or "filesystem access denied")
        return result.real_path


def _safe_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id is required")
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in task_id.strip())
    if safe in {".", ".."} or not safe:
        raise ValueError("task_id is invalid")
    return safe


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = [
    "FileAccessAction",
    "FileAccessAuditEntry",
    "FileAccessAuditor",
    "FileAccessDecision",
    "FilesystemJail",
    "FilesystemJailConfig",
    "FilesystemJailViolation",
    "PathValidationResult",
    "PathValidator",
    "VirtualWorkspace",
]
