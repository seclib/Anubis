"""Backend API and metrics aggregation for ANUBIS AI SOC dashboard."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol

from anubis.distributed.anomaly_engine import AnomalyFinding, RiskClassification, RiskScore
from anubis.distributed.kill_switch import KillSwitchController
from anubis.distributed.registry import AgentRegistry
from anubis.distributed.soc_event_ingestor import CentralSOCEventCollector, SOCEvent
from anubis.distributed.soc_response_engine import EnforcementController, SOCResponseActionType, SOCResponseEngine, SOCResponseResult


class DashboardRoute(StrEnum):
    STATUS = "/status"
    THREATS = "/threats"
    AGENTS = "/agents"
    EVENTS = "/events"


@dataclass(frozen=True)
class AgentSecurityMetric:
    agent_id: str
    active: bool
    risk_score: int = 0
    event_count: int = 0
    threat_count: int = 0
    blocked_action_count: int = 0
    throttled: bool = False
    monitored: bool = False
    last_seen: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "active": self.active,
            "risk_score": self.risk_score,
            "event_count": self.event_count,
            "threat_count": self.threat_count,
            "blocked_action_count": self.blocked_action_count,
            "throttled": self.throttled,
            "monitored": self.monitored,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


@dataclass(frozen=True)
class ThreatMetric:
    threat_id: str
    task_id: str
    agent_id: str
    score: int
    code: str
    category: str
    reason: str
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_id": self.threat_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "score": self.score,
            "code": self.code,
            "category": self.category,
            "reason": self.reason,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class SOCDashboardStatus:
    active_agents: int
    active_threats: int
    blocked_actions: int
    total_events: int
    max_risk_score: int
    kill_switch_status: dict[str, Any]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_agents": self.active_agents,
            "active_threats": self.active_threats,
            "blocked_actions": self.blocked_actions,
            "total_events": self.total_events,
            "max_risk_score": self.max_risk_score,
            "kill_switch_status": dict(self.kill_switch_status),
            "generated_at": self.generated_at.isoformat(),
        }


class LiveFeedSink(Protocol):
    def __call__(self, payload: dict[str, Any]) -> None: ...


class SOCLiveFeed:
    """In-process live feed for SOC events and alert payloads."""

    def __init__(self, *, max_history: int = 200) -> None:
        self.max_history = max_history
        self._subscribers: list[LiveFeedSink] = []
        self._history: list[dict[str, Any]] = []
        self._lock = RLock()

    def subscribe(self, sink: LiveFeedSink) -> None:
        if not callable(sink):
            raise ValueError("sink must be callable")
        with self._lock:
            self._subscribers.append(sink)

    def publish(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        message = {
            "kind": kind,
            "payload": dict(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._history.append(message)
            self._history = self._history[-self.max_history :]
            subscribers = tuple(self._subscribers)
        for sink in subscribers:
            sink(message)
        return message

    def history(self, *, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        with self._lock:
            items = self._history if limit is None else self._history[-limit:]
            return tuple(dict(item) for item in items)


class SOCMetricsAggregator:
    """Builds dashboard metrics from SOC events, anomaly findings, and enforcement state."""

    def __init__(
        self,
        *,
        collector: CentralSOCEventCollector | None = None,
        response_engine: SOCResponseEngine | None = None,
        kill_switch: KillSwitchController | None = None,
        agent_registry: AgentRegistry | None = None,
        live_feed: SOCLiveFeed | None = None,
    ) -> None:
        self.collector = collector or CentralSOCEventCollector()
        self.response_engine = response_engine or SOCResponseEngine()
        self.kill_switch = kill_switch or self.response_engine.kill_switch
        self.agent_registry = agent_registry
        self.live_feed = live_feed or SOCLiveFeed()
        self._classifications: list[RiskClassification] = []
        self._responses: list[SOCResponseResult] = []
        self._lock = RLock()

    def record_event(self, event: SOCEvent) -> SOCEvent:
        self.live_feed.publish("event", event.to_dict())
        return event

    def record_classification(self, classification: RiskClassification) -> RiskClassification:
        with self._lock:
            self._classifications.append(classification)
        self.live_feed.publish("alert", classification.to_dict())
        return classification

    def record_response(self, response: SOCResponseResult) -> SOCResponseResult:
        with self._lock:
            self._responses.append(response)
        self.live_feed.publish("response", response.to_dict())
        return response

    def status(self) -> SOCDashboardStatus:
        agents = self.agents()
        threats = self.threats(active_only=True)
        blocked = self.blocked_actions()
        return SOCDashboardStatus(
            active_agents=sum(1 for metric in agents if metric.active),
            active_threats=len(threats),
            blocked_actions=len(blocked),
            total_events=len(self.events()),
            max_risk_score=max((metric.risk_score for metric in agents), default=0),
            kill_switch_status=self.kill_switch.status().to_dict(),
        )

    def agents(self) -> tuple[AgentSecurityMetric, ...]:
        events = self.events()
        event_count: dict[str, int] = defaultdict(int)
        last_seen: dict[str, datetime] = {}
        for event in events:
            event_count[event.agent_id] += 1
            last_seen[event.agent_id] = event.timestamp

        threats_by_agent: dict[str, list[ThreatMetric]] = defaultdict(list)
        for threat in self.threats(active_only=False):
            threats_by_agent[threat.agent_id].append(threat)

        enforcement = self.response_engine.enforcement.state()
        registry_agents = set()
        if self.agent_registry is not None:
            registry_agents = {registration.agent_id for registration in self.agent_registry.list_agents()}
        ids = set(event_count) | set(threats_by_agent) | registry_agents | set(enforcement.throttled_agents) | set(enforcement.monitored_agents)

        metrics = []
        for agent_id in sorted(ids):
            threats = threats_by_agent.get(agent_id, [])
            metrics.append(
                AgentSecurityMetric(
                    agent_id=agent_id,
                    active=agent_id in registry_agents or agent_id in event_count,
                    risk_score=max((threat.score for threat in threats), default=0),
                    event_count=event_count.get(agent_id, 0),
                    threat_count=len([threat for threat in threats if threat.active]),
                    blocked_action_count=sum(1 for action in enforcement.actions if action.agent_id == agent_id and _is_blocking_action(action.action_type)),
                    throttled=agent_id in enforcement.throttled_agents,
                    monitored=agent_id in enforcement.monitored_agents,
                    last_seen=last_seen.get(agent_id),
                )
            )
        return tuple(metrics)

    def threats(self, *, active_only: bool = True) -> tuple[ThreatMetric, ...]:
        with self._lock:
            classifications = tuple(self._classifications)
        threats: list[ThreatMetric] = []
        for classification in classifications:
            for index, finding in enumerate(classification.findings):
                threat = _threat_from_finding(finding, index=index)
                if not active_only or threat.active:
                    threats.append(threat)
        threats.sort(key=lambda threat: (threat.score, threat.created_at.isoformat()), reverse=True)
        return tuple(threats)

    def blocked_actions(self) -> tuple[dict[str, Any], ...]:
        actions = self.response_engine.enforcement.state().actions
        return tuple(action.to_dict() for action in actions if _is_blocking_action(action.action_type))

    def events(self, *, limit: int | None = None) -> tuple[SOCEvent, ...]:
        events = self.collector.events()
        return events if limit is None else events[-limit:]


class SOCDashboardAPI:
    """Framework-neutral realtime API layer for SOC dashboard routes."""

    def __init__(self, aggregator: SOCMetricsAggregator) -> None:
        self.aggregator = aggregator

    def handle(self, path: str, *, query: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        query = dict(query or {})
        if path == DashboardRoute.STATUS:
            return 200, self.status()
        if path == DashboardRoute.THREATS:
            return 200, self.threats(active_only=query.get("active_only", True))
        if path == DashboardRoute.AGENTS:
            return 200, self.agents()
        if path == DashboardRoute.EVENTS:
            return 200, self.events(limit=query.get("limit"))
        return 404, {"error": "not found", "path": path}

    def status(self) -> dict[str, Any]:
        return self.aggregator.status().to_dict()

    def threats(self, *, active_only: bool = True) -> dict[str, Any]:
        return {"threats": [threat.to_dict() for threat in self.aggregator.threats(active_only=active_only)]}

    def agents(self) -> dict[str, Any]:
        return {"agents": [agent.to_dict() for agent in self.aggregator.agents()]}

    def events(self, *, limit: int | str | None = None) -> dict[str, Any]:
        normalized_limit = int(limit) if limit is not None else None
        return {"events": [event.to_dict() for event in self.aggregator.events(limit=normalized_limit)]}

    def live_feed(self, *, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        return self.aggregator.live_feed.history(limit=limit)

    def subscribe_live_feed(self, sink: LiveFeedSink) -> None:
        self.aggregator.live_feed.subscribe(sink)


def _threat_from_finding(finding: AnomalyFinding, *, index: int) -> ThreatMetric:
    sequence = finding.event.sequence if finding.event.sequence is not None else 0
    return ThreatMetric(
        threat_id=f"threat-{finding.task_id}-{finding.agent_id}-{sequence}-{index}",
        task_id=finding.task_id,
        agent_id=finding.agent_id,
        score=int(finding.score),
        code=finding.code.value,
        category=finding.category.value,
        reason=finding.reason,
        active=True,
        created_at=finding.event.timestamp,
    )


def _is_blocking_action(action_type: SOCResponseActionType) -> bool:
    return action_type in {
        SOCResponseActionType.THROTTLE_AGENT,
        SOCResponseActionType.PAUSE_TASK,
        SOCResponseActionType.ISOLATE_SANDBOX,
        SOCResponseActionType.TRIGGER_KILL_SWITCH,
        SOCResponseActionType.FREEZE_SYSTEM_STATE,
    }


__all__ = [
    "AgentSecurityMetric",
    "DashboardRoute",
    "LiveFeedSink",
    "SOCDashboardAPI",
    "SOCDashboardStatus",
    "SOCLiveFeed",
    "SOCMetricsAggregator",
    "ThreatMetric",
]
