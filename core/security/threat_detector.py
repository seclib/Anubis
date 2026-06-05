"""Deterministic threat detection over ANUBIS security audit records."""

from __future__ import annotations

from dataclasses import dataclass

from core.security.audit_logger import AuditLogger, AuditRecord
from core.security.kill_switch import KillSwitch, KillSwitchReason


@dataclass(frozen=True, slots=True)
class ThreatFinding:
    code: str
    severity: str
    actor: str
    detail: str
    count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "actor": self.actor,
            "detail": self.detail,
            "count": self.count,
        }


class ThreatDetector:
    """Conservative audit-based detector with deterministic thresholds."""

    def __init__(
        self,
        *,
        audit_logger: AuditLogger,
        kill_switch: KillSwitch,
        denial_threshold: int = 3,
    ) -> None:
        if denial_threshold < 1:
            raise ValueError("denial_threshold must be positive")
        self.audit_logger = audit_logger
        self.kill_switch = kill_switch
        self.denial_threshold = denial_threshold

    def scan(self) -> tuple[ThreatFinding, ...]:
        records = self.audit_logger.records()
        findings: list[ThreatFinding] = []
        findings.extend(self._repeated_denials(records))
        findings.extend(self._sandbox_escape_attempts(records))
        return tuple(sorted(findings, key=lambda item: (item.severity, item.actor, item.code)))

    def enforce(self) -> tuple[ThreatFinding, ...]:
        findings = self.scan()
        for finding in findings:
            if finding.severity == "critical" and not self.kill_switch.active:
                reason = (
                    KillSwitchReason.SANDBOX_ESCAPE_ATTEMPT
                    if finding.code == "sandbox_escape_attempt"
                    else KillSwitchReason.REPEATED_DENIALS
                )
                self.kill_switch.trigger(
                    reason=reason,
                    triggered_by=finding.actor,
                    detail=finding.detail,
                    metadata=finding.to_dict(),
                )
        return findings

    def _repeated_denials(self, records: tuple[AuditRecord, ...]) -> tuple[ThreatFinding, ...]:
        denied_by_actor: dict[str, int] = {}
        for record in records:
            if not record.allowed:
                denied_by_actor[record.actor] = denied_by_actor.get(record.actor, 0) + 1
        return tuple(
            ThreatFinding(
                code="repeated_denials",
                severity="critical",
                actor=actor,
                detail=f"Actor accumulated {count} denied security decision(s).",
                count=count,
            )
            for actor, count in sorted(denied_by_actor.items())
            if count >= self.denial_threshold
        )

    @staticmethod
    def _sandbox_escape_attempts(records: tuple[AuditRecord, ...]) -> tuple[ThreatFinding, ...]:
        findings: list[ThreatFinding] = []
        for record in records:
            reason = record.reason.lower()
            if "source modification" in reason or "filesystem must be sandbox_only" in reason:
                findings.append(
                    ThreatFinding(
                        code="sandbox_escape_attempt",
                        severity="critical",
                        actor=record.actor,
                        detail=record.reason,
                        count=1,
                    )
                )
        return tuple(findings)


SafetyMonitor = ThreatDetector


__all__ = ["SafetyMonitor", "ThreatDetector", "ThreatFinding"]
