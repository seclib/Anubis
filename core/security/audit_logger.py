"""Append-only audit logging for ANUBIS security decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from types import MappingProxyType
from typing import Any, Mapping

from core.security.permission_engine import PermissionDecision


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class AuditRecord:
    sequence: int
    actor: str
    action: str
    resource: str
    allowed: bool
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    previous_hash: str = "GENESIS"
    record_hash: str = ""

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if not self.record_hash:
            object.__setattr__(self, "record_hash", self.compute_hash())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "allowed": self.allowed,
            "reason": self.reason,
            "metadata": dict(sorted(self.metadata.items())),
            "timestamp": self.timestamp.isoformat(),
            "previous_hash": self.previous_hash,
        }

    def compute_hash(self) -> str:
        encoded = dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "record_hash": self.record_hash}


class AuditLogger:
    """Append-only hash-chained audit log."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        allowed: bool,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        previous_hash = self._records[-1].record_hash if self._records else "GENESIS"
        record = AuditRecord(
            sequence=len(self._records) + 1,
            actor=actor,
            action=action,
            resource=resource,
            allowed=allowed,
            reason=reason,
            metadata=metadata or {},
            previous_hash=previous_hash,
        )
        self._records.append(record)
        return record

    def append_decision(
        self,
        decision: PermissionDecision,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        return self.append(
            actor=decision.request.actor,
            action=decision.request.action,
            resource=decision.request.resource,
            allowed=decision.allowed,
            reason=decision.reason,
            metadata={
                "required_permissions": sorted(decision.request.required_permissions),
                "missing_permissions": sorted(decision.missing_permissions),
                **dict(metadata or {}),
            },
        )

    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def verify(self) -> bool:
        previous_hash = "GENESIS"
        for index, record in enumerate(self._records, start=1):
            if record.sequence != index:
                return False
            if record.previous_hash != previous_hash:
                return False
            if record.record_hash != record.compute_hash():
                return False
            previous_hash = record.record_hash
        return True


SelfAuditLog = AuditLogger


__all__ = ["AuditLogger", "AuditRecord", "SelfAuditLog"]
