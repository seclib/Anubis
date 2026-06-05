from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from anubis.events import EventBus
from anubis.types import Event, EventType, utcnow


class IntegrityStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class TamperSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    sequence: int
    actor: str
    action: str
    target: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    hash: str = ""
    timestamp: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class IntegrityArtifact:
    name: str
    digest: str
    algorithm: str = "sha256"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class IntegritySnapshot:
    artifacts: tuple[IntegrityArtifact, ...]
    root_hash: str
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    name: str
    status: IntegrityStatus
    expected: str | None
    actual: str | None
    explanation: str


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    status: IntegrityStatus
    findings: tuple[IntegrityFinding, ...]
    snapshot_root_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))


@dataclass(frozen=True, slots=True)
class TamperFinding:
    name: str
    severity: TamperSeverity
    explanation: str
    expected: str | None
    actual: str | None


class SelfAuditLog:
    """Append-only audit log with deterministic hash chaining."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        payload: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        previous_hash = self._records[-1].hash if self._records else ""
        sequence = len(self._records) + 1
        draft = AuditRecord(
            sequence=sequence,
            actor=actor,
            action=action,
            target=target,
            payload=payload or {},
            previous_hash=previous_hash,
        )
        digest = _hash_mapping(_audit_payload(draft))
        record = AuditRecord(
            sequence=draft.sequence,
            actor=draft.actor,
            action=draft.action,
            target=draft.target,
            payload=draft.payload,
            previous_hash=draft.previous_hash,
            hash=digest,
            timestamp=draft.timestamp,
        )
        self._records.append(record)
        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.AUDIT_RECORD_CREATED,
                    producer="audit",
                    payload={
                        "sequence": record.sequence,
                        "actor": record.actor,
                        "action": record.action,
                        "target": record.target,
                        "hash": record.hash,
                        "previous_hash": record.previous_hash,
                    },
                )
            )
        return record

    def verify_chain(self) -> IntegrityReport:
        findings: list[IntegrityFinding] = []
        previous_hash = ""
        for record in self._records:
            expected_hash = _hash_mapping(_audit_payload(record))
            if record.previous_hash != previous_hash:
                findings.append(
                    IntegrityFinding(
                        name=f"audit:{record.sequence}:previous_hash",
                        status=IntegrityStatus.FAIL,
                        expected=previous_hash,
                        actual=record.previous_hash,
                        explanation="Audit chain previous_hash does not match prior record.",
                    )
                )
            if record.hash != expected_hash:
                findings.append(
                    IntegrityFinding(
                        name=f"audit:{record.sequence}:hash",
                        status=IntegrityStatus.FAIL,
                        expected=expected_hash,
                        actual=record.hash,
                        explanation="Audit record hash does not match canonical content.",
                    )
                )
            previous_hash = record.hash

        status = IntegrityStatus.FAIL if findings else IntegrityStatus.PASS
        return IntegrityReport(
            status=status,
            findings=tuple(findings),
            snapshot_root_hash=previous_hash,
        )


class IntegrityChecker:
    """Creates and verifies hash snapshots for files and in-memory artifacts."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    def artifact_from_bytes(
        self,
        name: str,
        content: bytes,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> IntegrityArtifact:
        return IntegrityArtifact(
            name=name,
            digest=hashlib.sha256(content).hexdigest(),
            metadata=metadata or {},
        )

    def artifact_from_file(self, path: str | Path) -> IntegrityArtifact:
        file_path = Path(path)
        return self.artifact_from_bytes(
            str(file_path),
            file_path.read_bytes(),
            metadata={"size": file_path.stat().st_size},
        )

    def snapshot(self, artifacts: tuple[IntegrityArtifact, ...]) -> IntegritySnapshot:
        ordered = tuple(sorted(artifacts, key=lambda artifact: artifact.name))
        root_hash = _hash_mapping(
            {
                "artifacts": [
                    {
                        "name": artifact.name,
                        "digest": artifact.digest,
                        "algorithm": artifact.algorithm,
                    }
                    for artifact in ordered
                ]
            }
        )
        return IntegritySnapshot(artifacts=ordered, root_hash=root_hash)

    async def verify(
        self,
        trusted: IntegritySnapshot,
        current: IntegritySnapshot,
    ) -> IntegrityReport:
        trusted_by_name = {artifact.name: artifact for artifact in trusted.artifacts}
        current_by_name = {artifact.name: artifact for artifact in current.artifacts}
        findings: list[IntegrityFinding] = []

        for name in sorted(set(trusted_by_name) | set(current_by_name)):
            expected = trusted_by_name.get(name)
            actual = current_by_name.get(name)
            if expected is None:
                findings.append(
                    IntegrityFinding(
                        name=name,
                        status=IntegrityStatus.FAIL,
                        expected=None,
                        actual=actual.digest if actual else None,
                        explanation="Unexpected artifact appeared.",
                    )
                )
            elif actual is None:
                findings.append(
                    IntegrityFinding(
                        name=name,
                        status=IntegrityStatus.FAIL,
                        expected=expected.digest,
                        actual=None,
                        explanation="Expected artifact is missing.",
                    )
                )
            elif expected.digest != actual.digest:
                findings.append(
                    IntegrityFinding(
                        name=name,
                        status=IntegrityStatus.FAIL,
                        expected=expected.digest,
                        actual=actual.digest,
                        explanation="Artifact digest changed.",
                    )
                )

        status = IntegrityStatus.FAIL if findings else IntegrityStatus.PASS
        report = IntegrityReport(
            status=status,
            findings=tuple(findings),
            snapshot_root_hash=current.root_hash,
        )
        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.INTEGRITY_CHECK_COMPLETED,
                    producer="integrity",
                    payload={
                        "status": report.status.value,
                        "findings": len(report.findings),
                        "snapshot_root_hash": report.snapshot_root_hash,
                    },
                )
            )
        return report


class TamperDetector:
    """Converts failed integrity reports into severity-ranked tamper findings."""

    def __init__(self, *, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus

    async def detect(self, report: IntegrityReport) -> tuple[TamperFinding, ...]:
        findings = tuple(
            TamperFinding(
                name=finding.name,
                severity=self._severity_for(finding),
                explanation=finding.explanation,
                expected=finding.expected,
                actual=finding.actual,
            )
            for finding in report.findings
        )
        if findings and self.event_bus is not None:
            for finding in findings:
                await self.event_bus.publish(
                    Event(
                        type=EventType.TAMPER_DETECTED,
                        producer="integrity",
                        payload={
                            "name": finding.name,
                            "severity": finding.severity.value,
                            "explanation": finding.explanation,
                            "expected": finding.expected,
                            "actual": finding.actual,
                        },
                    )
                )
        return findings

    def _severity_for(self, finding: IntegrityFinding) -> TamperSeverity:
        if finding.actual is None:
            return TamperSeverity.CRITICAL
        if finding.expected is None:
            return TamperSeverity.HIGH
        if finding.name.startswith("audit:"):
            return TamperSeverity.CRITICAL
        return TamperSeverity.HIGH


def _audit_payload(record: AuditRecord) -> Mapping[str, Any]:
    return {
        "sequence": record.sequence,
        "actor": record.actor,
        "action": record.action,
        "target": record.target,
        "payload": dict(record.payload),
        "previous_hash": record.previous_hash,
        "timestamp": record.timestamp.isoformat(),
    }


def _hash_mapping(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
