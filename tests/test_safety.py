from __future__ import annotations

from datetime import timedelta

from anubis import (
    AgentBehaviorScore,
    AnomalyKind,
    Event,
    EventType,
    InMemoryEventBus,
    KillSwitchReason,
    SafetyMonitor,
    SafetyPolicy,
    utcnow,
)


def test_scores_suspicious_agent_behavior_from_events() -> None:
    monitor = SafetyMonitor()

    score = monitor.evaluate_event(
        Event(
            type=EventType.SANDBOX_DENIED,
            producer="test",
            agent_name="agent",
            payload={"missing_capabilities": ["network.scan"]},
        )
    )

    assert isinstance(score, AgentBehaviorScore)
    assert score.score == 30
    assert score.sandbox_denials == 1


def test_event_rate_anomaly_adds_risk() -> None:
    monitor = SafetyMonitor(
        policy=SafetyPolicy(max_events_per_window=2, event_window_seconds=60)
    )
    now = utcnow()

    for index in range(3):
        score = monitor.evaluate_event(
            Event(
                type=EventType.EXECUTION_ATTEMPT_FAILED,
                producer="test",
                agent_name="agent",
                payload={},
                timestamp=now + timedelta(seconds=index),
            )
        )

    assert score.score == 40
    assert score.anomalies[-1].kind == AnomalyKind.EVENT_RATE


def test_repeated_sandbox_denials_trigger_kill_switch() -> None:
    monitor = SafetyMonitor(policy=SafetyPolicy(sandbox_denial_threshold=3))

    for _ in range(3):
        score = monitor.evaluate_event(
            Event(
                type=EventType.SANDBOX_DENIED,
                producer="test",
                agent_name="agent",
                payload={},
            )
        )

    decision = monitor.evaluate_kill_switch(score)

    assert decision.triggered is True
    assert decision.reason == KillSwitchReason.REPEATED_SANDBOX_DENIALS
    assert monitor.triggered_agents() == ("agent",)


def test_rollback_failure_is_critical_kill_switch_anomaly() -> None:
    monitor = SafetyMonitor()

    score = monitor.evaluate_event(
        Event(
            type=EventType.EXECUTION_ROLLBACK_FAILED,
            producer="test",
            agent_name="agent",
            payload={},
        )
    )
    decision = monitor.evaluate_kill_switch(score)

    assert score.score == 75
    assert score.anomalies[-1].kind == AnomalyKind.ROLLBACK_FAILURE
    assert decision.triggered is True
    assert decision.reason == KillSwitchReason.CRITICAL_ANOMALY


async def test_monitor_publishes_score_anomaly_and_kill_switch_events() -> None:
    bus = InMemoryEventBus()
    monitor = SafetyMonitor(
        event_bus=bus,
        policy=SafetyPolicy(sandbox_denial_threshold=2),
    )
    monitor.attach()

    await bus.publish(
        Event(
            type=EventType.SANDBOX_DENIED,
            producer="test",
            agent_name="agent",
            payload={},
        )
    )
    await bus.publish(
        Event(
            type=EventType.SANDBOX_DENIED,
            producer="test",
            agent_name="agent",
            payload={},
        )
    )

    event_types = [event.type for event in bus.events]

    assert event_types.count(EventType.SAFETY_AGENT_SCORE_UPDATED) == 2
    assert EventType.SAFETY_ANOMALY_DETECTED in event_types
    assert EventType.SAFETY_KILL_SWITCH_TRIGGERED in event_types
    assert monitor.triggered_agents() == ("agent",)

