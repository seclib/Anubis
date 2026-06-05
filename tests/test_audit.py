from __future__ import annotations

from dataclasses import replace

from anubis import (
    EventType,
    InMemoryEventBus,
    IntegrityChecker,
    IntegrityStatus,
    SelfAuditLog,
    TamperDetector,
    TamperSeverity,
)


async def test_self_audit_log_hash_chain_verifies() -> None:
    audit = SelfAuditLog()

    first = await audit.record(
        actor="orchestrator",
        action="submit",
        target="task-1",
        payload={"kind": "scan"},
    )
    second = await audit.record(
        actor="execution",
        action="start",
        target="task-1",
    )
    report = audit.verify_chain()

    assert first.previous_hash == ""
    assert second.previous_hash == first.hash
    assert report.status == IntegrityStatus.PASS
    assert report.findings == ()


async def test_self_audit_log_detects_tampered_record() -> None:
    audit = SelfAuditLog()
    record = await audit.record(actor="agent", action="write", target="memory")
    audit._records[0] = replace(record, action="delete")

    report = audit.verify_chain()

    assert report.status == IntegrityStatus.FAIL
    assert report.findings[0].name == "audit:1:hash"


async def test_audit_record_publishes_event() -> None:
    bus = InMemoryEventBus()
    audit = SelfAuditLog(event_bus=bus)

    await audit.record(actor="agent", action="read", target="memory")

    assert bus.events[0].type == EventType.AUDIT_RECORD_CREATED
    assert bus.events[0].payload["sequence"] == 1


async def test_integrity_checker_reports_changed_missing_and_unexpected_artifacts() -> None:
    checker = IntegrityChecker()
    trusted = checker.snapshot(
        (
            checker.artifact_from_bytes("a", b"one"),
            checker.artifact_from_bytes("b", b"two"),
        )
    )
    current = checker.snapshot(
        (
            checker.artifact_from_bytes("a", b"changed"),
            checker.artifact_from_bytes("c", b"three"),
        )
    )

    report = await checker.verify(trusted, current)

    assert report.status == IntegrityStatus.FAIL
    assert {finding.name for finding in report.findings} == {"a", "b", "c"}


async def test_tamper_detector_emits_ranked_findings_and_events() -> None:
    bus = InMemoryEventBus()
    checker = IntegrityChecker(event_bus=bus)
    detector = TamperDetector(event_bus=bus)
    trusted = checker.snapshot((checker.artifact_from_bytes("critical", b"ok"),))
    current = checker.snapshot(())

    report = await checker.verify(trusted, current)
    findings = await detector.detect(report)

    assert findings[0].name == "critical"
    assert findings[0].severity == TamperSeverity.CRITICAL
    assert EventType.INTEGRITY_CHECK_COMPLETED in [event.type for event in bus.events]
    assert EventType.TAMPER_DETECTED in [event.type for event in bus.events]

