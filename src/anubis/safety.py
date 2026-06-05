from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Deque, Mapping, Sequence

from anubis.events import EventBus
from anubis.types import Event, EventType, utcnow


class AnomalyKind(StrEnum):
    EVENT_RATE = "event_rate"
    SANDBOX_DENIALS = "sandbox_denials"
    REPEATED_FAILURES = "repeated_failures"
    ROLLBACK_FAILURE = "rollback_failure"


class KillSwitchReason(StrEnum):
    RISK_THRESHOLD = "risk_threshold"
    CRITICAL_ANOMALY = "critical_anomaly"
    REPEATED_SANDBOX_DENIALS = "repeated_sandbox_denials"


@dataclass(frozen=True, slots=True)
class Anomaly:
    kind: AnomalyKind
    agent_name: str
    score_delta: float
    explanation: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentBehaviorScore:
    agent_name: str
    score: float = 0
    sandbox_denials: int = 0
    task_failures: int = 0
    rollback_failures: int = 0
    anomalies: tuple[Anomaly, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        object.__setattr__(self, "anomalies", tuple(self.anomalies))


@dataclass(frozen=True, slots=True)
class KillSwitchDecision:
    triggered: bool
    agent_name: str
    reason: KillSwitchReason | None
    score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    kill_score_threshold: float = 75
    max_events_per_window: int = 10
    event_window_seconds: float = 60
    sandbox_denial_threshold: int = 3
    failure_threshold: int = 4

    def __post_init__(self) -> None:
        if not 0 <= self.kill_score_threshold <= 100:
            raise ValueError("kill_score_threshold must be between 0 and 100")
        if self.max_events_per_window < 1:
            raise ValueError("max_events_per_window must be at least 1")
        if self.event_window_seconds <= 0:
            raise ValueError("event_window_seconds must be positive")
        if self.sandbox_denial_threshold < 1:
            raise ValueError("sandbox_denial_threshold must be at least 1")
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")


class SafetyMonitor:
    """Internal anomaly detector and kill-switch decision engine."""

    _event_weights = {
        EventType.EXECUTION_ATTEMPT_FAILED: 5,
        EventType.TASK_FAILED: 12,
        EventType.SANDBOX_DENIED: 30,
        EventType.EXECUTION_ROLLBACK_FAILED: 35,
        EventType.TASK_SUCCEEDED: -5,
        EventType.SANDBOX_ALLOWED: -2,
    }

    def __init__(
        self,
        *,
        policy: SafetyPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy()
        self.event_bus = event_bus
        self._scores: dict[str, AgentBehaviorScore] = {}
        self._event_history: dict[str, Deque[Event]] = defaultdict(deque)
        self._triggered_agents: set[str] = set()
        self._subscription_id: str | None = None

    def attach(self, event_bus: EventBus | None = None) -> str:
        bus = event_bus or self.event_bus
        if bus is None:
            raise ValueError("event bus is required")
        self.event_bus = bus
        self._subscription_id = bus.subscribe(None, self.handle_event)
        return self._subscription_id

    async def handle_event(self, event: Event) -> KillSwitchDecision | None:
        if event.type in {
            EventType.SAFETY_ANOMALY_DETECTED,
            EventType.SAFETY_AGENT_SCORE_UPDATED,
            EventType.SAFETY_KILL_SWITCH_TRIGGERED,
        }:
            return None
        if event.agent_name is None:
            return None
        previous_anomaly_count = len(self.score_for(event.agent_name).anomalies)
        score = self.evaluate_event(event)
        new_anomalies = score.anomalies[previous_anomaly_count:]
        await self._publish_score(score, new_anomalies)
        decision = self.evaluate_kill_switch(score)
        if decision.triggered:
            await self._publish_kill_switch(decision)
        return decision

    def evaluate_event(self, event: Event) -> AgentBehaviorScore:
        if event.agent_name is None:
            raise ValueError("event must include agent_name")

        current = self._scores.get(
            event.agent_name,
            AgentBehaviorScore(agent_name=event.agent_name),
        )
        anomalies = list(current.anomalies)
        delta = self._event_weights.get(event.type, 0)
        sandbox_denials = current.sandbox_denials + (1 if event.type == EventType.SANDBOX_DENIED else 0)
        task_failures = current.task_failures + (1 if event.type == EventType.TASK_FAILED else 0)
        rollback_failures = current.rollback_failures + (
            1 if event.type == EventType.EXECUTION_ROLLBACK_FAILED else 0
        )

        new_anomalies = self._detect_anomalies(
            event=event,
            sandbox_denials=sandbox_denials,
            task_failures=task_failures,
            rollback_failures=rollback_failures,
        )
        anomalies.extend(new_anomalies)
        delta += sum(anomaly.score_delta for anomaly in new_anomalies)

        next_score = min(100.0, max(0.0, current.score + delta))
        score = replace(
            current,
            score=next_score,
            sandbox_denials=sandbox_denials,
            task_failures=task_failures,
            rollback_failures=rollback_failures,
            anomalies=tuple(anomalies),
        )
        self._scores[event.agent_name] = score
        return score

    def evaluate_kill_switch(self, score: AgentBehaviorScore) -> KillSwitchDecision:
        if score.agent_name in self._triggered_agents:
            return KillSwitchDecision(
                triggered=False,
                agent_name=score.agent_name,
                reason=None,
                score=score.score,
                explanation="Kill-switch already triggered for this agent.",
            )

        reason: KillSwitchReason | None = None
        if score.sandbox_denials >= self.policy.sandbox_denial_threshold:
            reason = KillSwitchReason.REPEATED_SANDBOX_DENIALS
        elif score.anomalies and score.anomalies[-1].kind == AnomalyKind.ROLLBACK_FAILURE:
            reason = KillSwitchReason.CRITICAL_ANOMALY
        elif score.score >= self.policy.kill_score_threshold:
            reason = KillSwitchReason.RISK_THRESHOLD

        if reason is None:
            return KillSwitchDecision(
                triggered=False,
                agent_name=score.agent_name,
                reason=None,
                score=score.score,
                explanation="Agent risk remains below kill-switch thresholds.",
            )

        self._triggered_agents.add(score.agent_name)
        return KillSwitchDecision(
            triggered=True,
            agent_name=score.agent_name,
            reason=reason,
            score=score.score,
            explanation=f"Kill-switch triggered for '{score.agent_name}' due to {reason}.",
        )

    def score_for(self, agent_name: str) -> AgentBehaviorScore:
        return self._scores.get(agent_name, AgentBehaviorScore(agent_name=agent_name))

    def triggered_agents(self) -> tuple[str, ...]:
        return tuple(sorted(self._triggered_agents))

    def _detect_anomalies(
        self,
        *,
        event: Event,
        sandbox_denials: int,
        task_failures: int,
        rollback_failures: int,
    ) -> tuple[Anomaly, ...]:
        anomalies: list[Anomaly] = []
        history = self._event_history[event.agent_name or ""]
        history.append(event)
        self._trim_history(history, event)

        if len(history) > self.policy.max_events_per_window:
            anomalies.append(
                Anomaly(
                    kind=AnomalyKind.EVENT_RATE,
                    agent_name=event.agent_name or "",
                    score_delta=25,
                    explanation=(
                        f"Agent emitted {len(history)} events inside "
                        f"{self.policy.event_window_seconds}s."
                    ),
                )
            )

        if event.type == EventType.SANDBOX_DENIED and sandbox_denials >= self.policy.sandbox_denial_threshold:
            anomalies.append(
                Anomaly(
                    kind=AnomalyKind.SANDBOX_DENIALS,
                    agent_name=event.agent_name or "",
                    score_delta=20,
                    explanation="Agent repeatedly requested denied sandbox capabilities.",
                    metadata={"sandbox_denials": sandbox_denials},
                )
            )

        if event.type == EventType.TASK_FAILED and task_failures >= self.policy.failure_threshold:
            anomalies.append(
                Anomaly(
                    kind=AnomalyKind.REPEATED_FAILURES,
                    agent_name=event.agent_name or "",
                    score_delta=15,
                    explanation="Agent repeatedly failed assigned tasks.",
                    metadata={"task_failures": task_failures},
                )
            )

        if event.type == EventType.EXECUTION_ROLLBACK_FAILED and rollback_failures >= 1:
            anomalies.append(
                Anomaly(
                    kind=AnomalyKind.ROLLBACK_FAILURE,
                    agent_name=event.agent_name or "",
                    score_delta=40,
                    explanation="Agent failed rollback, indicating unsafe execution behavior.",
                )
            )

        return tuple(anomalies)

    def _trim_history(self, history: Deque[Event], event: Event) -> None:
        cutoff = event.timestamp.timestamp() - self.policy.event_window_seconds
        while history and history[0].timestamp.timestamp() < cutoff:
            history.popleft()

    async def _publish_score(
        self,
        score: AgentBehaviorScore,
        anomalies: Sequence[Anomaly],
    ) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            Event(
                type=EventType.SAFETY_AGENT_SCORE_UPDATED,
                producer="safety",
                agent_name=score.agent_name,
                payload={
                    "score": score.score,
                    "sandbox_denials": score.sandbox_denials,
                    "task_failures": score.task_failures,
                    "rollback_failures": score.rollback_failures,
                },
            )
        )
        for anomaly in anomalies:
            await self.event_bus.publish(
                Event(
                    type=EventType.SAFETY_ANOMALY_DETECTED,
                    producer="safety",
                    agent_name=score.agent_name,
                    payload={
                        "kind": anomaly.kind.value,
                        "score_delta": anomaly.score_delta,
                        "explanation": anomaly.explanation,
                        "metadata": dict(anomaly.metadata),
                    },
                )
            )

    async def _publish_kill_switch(self, decision: KillSwitchDecision) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            Event(
                type=EventType.SAFETY_KILL_SWITCH_TRIGGERED,
                producer="safety",
                agent_name=decision.agent_name,
                payload={
                    "reason": decision.reason.value if decision.reason else None,
                    "score": decision.score,
                    "explanation": decision.explanation,
                    "triggered_at": utcnow().isoformat(),
                },
            )
        )
