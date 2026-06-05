from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.events import EventBus
from anubis.types import Event, EventType, utcnow


class ArchitectureSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RefactorStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ArchitectureRule:
    id: str
    description: str
    severity: ArchitectureSeverity


@dataclass(frozen=True, slots=True)
class ArchitectureFinding:
    rule_id: str
    path: str
    severity: ArchitectureSeverity
    message: str
    line: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class FileEdit:
    path: str
    before: str
    after: str
    base_hash: str
    prepend: bool = False

    @classmethod
    def replace(cls, path: str, original: str, before: str, after: str) -> "FileEdit":
        return cls(
            path=path,
            before=before,
            after=after,
            base_hash=_sha256_text(original),
        )

    @classmethod
    def prepend_text(cls, path: str, original: str, text: str) -> "FileEdit":
        return cls(
            path=path,
            before="",
            after=text,
            base_hash=_sha256_text(original),
            prepend=True,
        )


@dataclass(frozen=True, slots=True)
class RefactorProposal:
    id: str
    title: str
    rationale: str
    findings: tuple[ArchitectureFinding, ...]
    edits: tuple[FileEdit, ...]
    status: RefactorStatus = RefactorStatus.PROPOSED
    created_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "edits", tuple(self.edits))


@dataclass(frozen=True, slots=True)
class ChangeSetResult:
    proposal_id: str
    applied: bool
    changed_files: tuple[str, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    patch: str = ""
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "errors", tuple(self.errors))


class ArchitectureAnalyzer:
    """Static architecture detector for local Python modules."""

    def __init__(
        self,
        *,
        max_lines: int = 300,
        max_imports: int = 25,
        forbidden_imports: Mapping[str, tuple[str, ...]] | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.max_lines = max_lines
        self.max_imports = max_imports
        self.forbidden_imports = dict(forbidden_imports or {})
        self.event_bus = event_bus

    async def analyze_paths(self, paths: Sequence[str | Path]) -> tuple[ArchitectureFinding, ...]:
        findings: list[ArchitectureFinding] = []
        for path in sorted((Path(item) for item in paths), key=lambda item: str(item)):
            if path.is_dir():
                files = sorted(path.rglob("*.py"))
            else:
                files = [path]
            for file_path in files:
                findings.extend(self.analyze_file(file_path))

        result = tuple(findings)
        if self.event_bus is not None:
            for finding in result:
                await self.event_bus.publish(
                    Event(
                        type=EventType.ARCHITECTURE_FINDING_CREATED,
                        producer="architecture",
                        payload={
                            "rule_id": finding.rule_id,
                            "path": finding.path,
                            "severity": finding.severity.value,
                            "message": finding.message,
                            "line": finding.line,
                        },
                    )
                )
        return result

    def analyze_file(self, path: str | Path) -> tuple[ArchitectureFinding, ...]:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        findings: list[ArchitectureFinding] = []

        if len(lines) > self.max_lines:
            findings.append(
                ArchitectureFinding(
                    rule_id="module.too_large",
                    path=str(file_path),
                    severity=ArchitectureSeverity.WARNING,
                    message=f"Module has {len(lines)} lines; limit is {self.max_lines}.",
                    metadata={"line_count": len(lines), "limit": self.max_lines},
                )
            )

        tree = ast.parse(text)
        imports = _imports_from_tree(tree)
        if len(imports) > self.max_imports:
            findings.append(
                ArchitectureFinding(
                    rule_id="module.too_many_imports",
                    path=str(file_path),
                    severity=ArchitectureSeverity.WARNING,
                    message=f"Module imports {len(imports)} modules; limit is {self.max_imports}.",
                    metadata={"import_count": len(imports), "limit": self.max_imports},
                )
            )

        for source, forbidden in sorted(self.forbidden_imports.items()):
            if source not in str(file_path):
                continue
            for imported in sorted(imports):
                if imported.startswith(forbidden):
                    findings.append(
                        ArchitectureFinding(
                            rule_id="dependency.forbidden",
                            path=str(file_path),
                            severity=ArchitectureSeverity.ERROR,
                            message=f"Forbidden dependency from {source} to {imported}.",
                            metadata={"source": source, "import": imported},
                        )
                    )

        if not ast.get_docstring(tree):
            findings.append(
                ArchitectureFinding(
                    rule_id="module.missing_docstring",
                    path=str(file_path),
                    severity=ArchitectureSeverity.INFO,
                    message="Module is missing an architectural docstring.",
                    line=1,
                )
            )

        return tuple(findings)


class RefactorPlanner:
    """Turns architecture findings into deterministic reviewable proposals."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    async def propose(self, findings: Sequence[ArchitectureFinding]) -> tuple[RefactorProposal, ...]:
        proposals: list[RefactorProposal] = []
        by_path: dict[str, list[ArchitectureFinding]] = {}
        for finding in findings:
            by_path.setdefault(finding.path, []).append(finding)

        for path, path_findings in sorted(by_path.items()):
            docstring_findings = [
                finding for finding in path_findings if finding.rule_id == "module.missing_docstring"
            ]
            if not docstring_findings:
                continue
            file_path = Path(path)
            original = file_path.read_text(encoding="utf-8")
            module_name = file_path.stem.replace("_", " ")
            docstring = f'"""ANUBIS {module_name} module."""\n\n'
            edit = FileEdit.prepend_text(path, original, docstring)
            proposal = RefactorProposal(
                id=f"refactor_{uuid4().hex}",
                title=f"Add architecture docstring to {file_path.name}",
                rationale="A module docstring makes ownership and architectural intent explicit.",
                findings=tuple(docstring_findings),
                edits=(edit,),
            )
            proposals.append(proposal)

        result = tuple(proposals)
        if self.event_bus is not None:
            for proposal in result:
                await self.event_bus.publish(
                    Event(
                        type=EventType.REFACTOR_PROPOSED,
                        producer="architecture",
                        payload={
                            "proposal_id": proposal.id,
                            "title": proposal.title,
                            "edits": len(proposal.edits),
                            "findings": len(proposal.findings),
                        },
                    )
                )
        return result


class PullRequestSystem:
    """Generates PR-style patches without applying them at runtime."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    async def apply(self, proposal: RefactorProposal, *, root: str | Path = ".") -> ChangeSetResult:
        root_path = Path(root)
        errors: list[str] = []
        patch_parts: list[str] = []

        for edit in proposal.edits:
            path = root_path / edit.path if not Path(edit.path).is_absolute() else Path(edit.path)
            if not path.exists():
                errors.append(f"file does not exist: {edit.path}")
                continue
            current = path.read_text(encoding="utf-8")
            if _sha256_text(current) != edit.base_hash:
                errors.append(f"base hash mismatch: {edit.path}")
                continue
            if edit.prepend:
                patch_parts.append(_edit_to_diff(edit, current))
                continue
            if edit.before not in current:
                errors.append(f"edit context not found: {edit.path}")
                continue
            patch_parts.append(_edit_to_diff(edit, current))

        result = ChangeSetResult(
            proposal_id=proposal.id,
            applied=False,
            changed_files=(),
            errors=(
                *tuple(errors),
                "runtime source modification is disabled; patch requires human approval.",
            ),
            patch="\n".join(part for part in patch_parts if part),
            requires_human_approval=True,
        )
        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.PATCH_PROPOSED,
                    producer="architecture",
                    payload={
                        "proposal_id": result.proposal_id,
                        "applied": result.applied,
                        "requires_human_approval": result.requires_human_approval,
                        "patch_bytes": len(result.patch.encode("utf-8")),
                        "errors": result.errors,
                    },
                )
            )
            await self.event_bus.publish(
                Event(
                    type=EventType.PATCH_REQUIRES_APPROVAL,
                    producer="architecture",
                    payload={
                        "proposal_id": result.proposal_id,
                        "reason": "All source changes require explicit human review.",
                    },
                )
            )
        return result


def _imports_from_tree(tree: ast.AST) -> tuple[str, ...]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return tuple(sorted(imports))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _edit_to_diff(edit: FileEdit, current: str) -> str:
    if edit.prepend:
        return (
            f"diff --git a/{edit.path} b/{edit.path}\n"
            f"--- a/{edit.path}\n"
            f"+++ b/{edit.path}\n"
            "@@ -1,0 +1 @@\n"
            + "".join(f"+{line}\n" for line in edit.after.splitlines())
        )
    replacement = current.replace(edit.before, edit.after, 1)
    return (
        f"diff --git a/{edit.path} b/{edit.path}\n"
        f"--- a/{edit.path}\n"
        f"+++ b/{edit.path}\n"
        f"@@ proposed safe refactor @@\n"
        f"-{edit.before}\n"
        f"+{edit.after}\n"
        f"# full_candidate_sha256={_sha256_text(replacement)}"
    )
