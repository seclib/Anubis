from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.self_improvement import SimulationResult, UpgradeProposal
from anubis.types import utcnow


@dataclass(frozen=True, slots=True)
class GenomeVersion:
    id: str
    parent_id: str | None
    reason: str
    diff: str
    performance_impact: Mapping[str, Any]
    rollback_reference: str
    proposal_id: str | None = None
    applied: bool = False
    created_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "performance_impact", MappingProxyType(dict(self.performance_impact)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "reason": self.reason,
            "diff": self.diff,
            "performance_impact": dict(self.performance_impact),
            "rollback_reference": self.rollback_reference,
            "proposal_id": self.proposal_id,
            "applied": self.applied,
            "created_at": str(self.created_at),
        }


class VersionControlTree:
    """Append-only deterministic evolution tree for simulated genome versions."""

    def __init__(
        self,
        *,
        root_id: str = "0.1.0",
        storage_path: str | Path | None = None,
    ) -> None:
        self.root_id = root_id
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._versions: dict[str, GenomeVersion] = {}
        self._children: dict[str | None, list[str]] = {None: [root_id], root_id: []}
        self._head = root_id
        self._load()

    @property
    def head(self) -> str:
        return self._head

    def versions(self) -> tuple[GenomeVersion, ...]:
        return tuple(self._versions[key] for key in sorted(self._versions))

    def record_candidate(
        self,
        proposal: UpgradeProposal,
        simulation: SimulationResult,
        *,
        fitness_before: Mapping[str, Any],
        parent_id: str | None = None,
    ) -> GenomeVersion:
        return self._append(
            parent_id=parent_id or self._head,
            reason=proposal.rationale,
            diff=_proposal_diff(proposal),
            performance_impact={
                "fitness_before": dict(fitness_before),
                "expected_score_delta": simulation.expected_score_delta,
                "simulation_safe": simulation.safe,
                "simulation": simulation.explanation,
            },
            rollback_reference="not-applied",
            proposal_id=proposal.id,
            applied=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root_id,
            "head": self._head,
            "versions": [version.to_dict() for version in self.versions()],
            "branches": {
                str(parent): tuple(children)
                for parent, children in sorted(self._children.items(), key=lambda item: str(item[0]))
            },
        }

    def _append(
        self,
        *,
        parent_id: str,
        reason: str,
        diff: str,
        performance_impact: Mapping[str, Any],
        rollback_reference: str,
        proposal_id: str | None,
        applied: bool,
    ) -> GenomeVersion:
        version = GenomeVersion(
            id=f"genome_{uuid4().hex}",
            parent_id=parent_id,
            reason=reason,
            diff=diff,
            performance_impact=performance_impact,
            rollback_reference=rollback_reference,
            proposal_id=proposal_id,
            applied=applied,
        )
        self._versions[version.id] = version
        self._children.setdefault(parent_id, []).append(version.id)
        self._children.setdefault(version.id, [])
        self._head = version.id
        self._persist()
        return version

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self.root_id = data.get("root", self.root_id)
        self._head = data.get("head", self.root_id)
        for item in data.get("versions", ()):
            version = GenomeVersion(
                id=item["id"],
                parent_id=item.get("parent_id"),
                reason=item["reason"],
                diff=item["diff"],
                performance_impact=item.get("performance_impact", {}),
                rollback_reference=item.get("rollback_reference", "unknown"),
                proposal_id=item.get("proposal_id"),
                applied=bool(item.get("applied", False)),
                created_at=item.get("created_at", ""),
            )
            self._versions[version.id] = version
            self._children.setdefault(version.parent_id, []).append(version.id)
            self._children.setdefault(version.id, [])

    def _persist(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _proposal_diff(proposal: UpgradeProposal) -> str:
    if proposal.refactor is None:
        return "No concrete file diff; policy/planning recommendation only."
    edits = []
    for edit in proposal.refactor.edits:
        if edit.prepend:
            edits.append(f"PREPEND {edit.path}: {edit.after!r}")
        else:
            edits.append(f"REPLACE {edit.path}: {edit.before!r} -> {edit.after!r}")
    return "\n".join(edits)
