"""Central security kernel for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.security.audit_logger import AuditLogger
from core.security.kill_switch import KillSwitch
from core.security.permission_engine import ActionRequest, PermissionDecision, PermissionEngine
from core.security.sandbox_guard import SandboxDecision, SandboxGuard, SandboxRequest
from core.security.threat_detector import ThreatDetector, ThreatFinding


@dataclass(slots=True)
class SecurityKernel:
    """Single security composition point for production modules."""

    permission_engine: PermissionEngine = field(default_factory=PermissionEngine)
    audit_logger: AuditLogger = field(default_factory=AuditLogger)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    sandbox_guard: SandboxGuard = field(init=False)
    threat_detector: ThreatDetector = field(init=False)

    def __post_init__(self) -> None:
        self.sandbox_guard = SandboxGuard(
            permission_engine=self.permission_engine,
            audit_logger=self.audit_logger,
            kill_switch=self.kill_switch,
        )
        self.threat_detector = ThreatDetector(
            audit_logger=self.audit_logger,
            kill_switch=self.kill_switch,
        )

    def authorize(self, request: ActionRequest) -> PermissionDecision:
        decision = self.permission_engine.validate(request)
        self.audit_logger.append_decision(decision, metadata={"component": "security_kernel"})
        self.threat_detector.enforce()
        return decision

    def validate_sandbox(self, request: SandboxRequest) -> SandboxDecision:
        decision = self.sandbox_guard.validate(request)
        self.threat_detector.enforce()
        return decision

    def scan_threats(self) -> tuple[ThreatFinding, ...]:
        return self.threat_detector.enforce()

    def snapshot(self) -> dict[str, object]:
        return {
            "kill_switch_active": self.kill_switch.active,
            "audit_records": len(self.audit_logger.records()),
            "permission_rules": len(self.permission_engine.rules()),
            "threat_findings": tuple(finding.to_dict() for finding in self.threat_detector.scan()),
        }


__all__ = ["SecurityKernel"]
