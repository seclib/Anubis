from __future__ import annotations

import inspect

from core.security import (
    ActionRequest,
    AuditLogger,
    FilesystemMode,
    KillSwitch,
    KillSwitchReason,
    NetworkMode,
    PermissionEffect,
    PermissionEngine,
    PermissionRule,
    SandboxGuard,
    SandboxRequest,
    ThreatDetector,
)
from core.security import kill_switch, permission_engine, sandbox_guard


def _security_stack() -> tuple[PermissionEngine, AuditLogger, KillSwitch, SandboxGuard]:
    permissions = PermissionEngine()
    audit = AuditLogger()
    kills = KillSwitch()
    guard = SandboxGuard(
        permission_engine=permissions,
        audit_logger=audit,
        kill_switch=kills,
    )
    return permissions, audit, kills, guard


def test_permission_engine_denies_by_default() -> None:
    engine = PermissionEngine()

    decision = engine.validate(
        ActionRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            required_permissions=frozenset({"sandbox.execute"}),
        )
    )

    assert decision.allowed is False
    assert "Denied by default" in decision.reason
    assert decision.missing_permissions == frozenset({"sandbox.execute"})


def test_permission_engine_allows_only_explicit_rules_and_denies_take_precedence() -> None:
    engine = PermissionEngine(
        rules=(
            PermissionRule(
                actor="executor_agent",
                actions=frozenset({"sandbox.run"}),
                resources=frozenset({"task"}),
                permissions=frozenset({"sandbox.execute"}),
                effect=PermissionEffect.ALLOW,
            ),
            PermissionRule(
                actor="executor_agent",
                actions=frozenset({"sandbox.run"}),
                resources=frozenset({"task"}),
                permissions=frozenset({"sandbox.execute"}),
                effect=PermissionEffect.DENY,
                reason="Maintenance lock.",
            ),
        )
    )

    decision = engine.validate(
        ActionRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            required_permissions=frozenset({"sandbox.execute"}),
        )
    )

    assert decision.allowed is False
    assert decision.reason == "Maintenance lock."


def test_wildcard_permission_rules_are_rejected() -> None:
    try:
        PermissionRule(
            actor="agent",
            actions=frozenset({"*"}),
            resources=frozenset({"task"}),
        )
    except ValueError as exc:
        assert "wildcard" in str(exc)
    else:
        raise AssertionError("expected wildcard rule rejection")


def test_audit_logger_is_append_only_and_hash_chained() -> None:
    audit = AuditLogger()

    first = audit.append(
        actor="planner",
        action="plan.create",
        resource="task_graph",
        allowed=True,
        reason="explicit allow",
    )
    second = audit.append(
        actor="executor",
        action="sandbox.run",
        resource="task",
        allowed=False,
        reason="denied by default",
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.record_hash
    assert audit.verify() is True
    assert audit.records() == (first, second)


def test_sandbox_guard_requires_permissions_and_sandbox_only_filesystem() -> None:
    permissions, audit, _kills, guard = _security_stack()
    permissions.add_rule(
        PermissionRule(
            actor="executor_agent",
            actions=frozenset({"sandbox.run"}),
            resources=frozenset({"task"}),
            permissions=frozenset({"sandbox.execute"}),
            effect=PermissionEffect.ALLOW,
        )
    )

    allowed = guard.validate(
        SandboxRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            operation="agent_task",
        )
    )
    denied = guard.validate(
        SandboxRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            operation="agent_task",
            filesystem=FilesystemMode.NONE,
        )
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "sandbox_only" in denied.reason
    assert len(audit.records()) == 2
    assert audit.verify() is True


def test_sandbox_guard_network_requires_explicit_permission() -> None:
    permissions, _audit, _kills, guard = _security_stack()
    permissions.add_rule(
        PermissionRule(
            actor="executor_agent",
            actions=frozenset({"sandbox.run"}),
            resources=frozenset({"task"}),
            permissions=frozenset({"sandbox.execute"}),
        )
    )

    decision = guard.validate(
        SandboxRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            operation="agent_task",
            network=NetworkMode.EXPLICIT,
        )
    )

    assert decision.allowed is False
    assert decision.permission_decision is not None
    assert "network.explicit" in decision.permission_decision.missing_permissions


def test_kill_switch_blocks_actions_after_trigger() -> None:
    permissions, audit, kills, guard = _security_stack()
    permissions.add_rule(
        PermissionRule(
            actor="executor_agent",
            actions=frozenset({"sandbox.run"}),
            resources=frozenset({"task"}),
            permissions=frozenset({"sandbox.execute"}),
        )
    )
    kills.trigger(
        reason=KillSwitchReason.MANUAL_SECURITY_STOP,
        triggered_by="security",
        detail="manual stop for test",
    )

    decision = guard.validate(
        SandboxRequest(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            operation="agent_task",
        )
    )

    assert decision.allowed is False
    assert "Kill switch active" in decision.reason
    assert audit.records()[-1].allowed is False
    assert kills.validate_action("security.status.read").allowed is True


def test_threat_detector_triggers_kill_switch_for_repeated_denials() -> None:
    _permissions, audit, kills, _guard = _security_stack()
    for _ in range(3):
        audit.append(
            actor="executor_agent",
            action="sandbox.run",
            resource="task",
            allowed=False,
            reason="Denied by default",
        )
    detector = ThreatDetector(
        audit_logger=audit,
        kill_switch=kills,
        denial_threshold=3,
    )

    findings = detector.enforce()

    assert len(findings) == 1
    assert findings[0].code == "repeated_denials"
    assert kills.active is True
    assert kills.event is not None
    assert kills.event.reason == KillSwitchReason.REPEATED_DENIALS


def test_security_modules_expose_no_bypass_or_reset_paths() -> None:
    sources = "\n".join(
        inspect.getsource(module)
        for module in (permission_engine, sandbox_guard, kill_switch)
    )

    for token in ("bypass", "allow_all", "disable_security", "reset("):
        assert token not in sources
