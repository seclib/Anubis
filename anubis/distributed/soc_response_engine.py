"""AI SOC response and mitigation engine for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any
from uuid import uuid4

from anubis.distributed.anomaly_engine import AnomalyFinding, RiskClassification, RiskScore
from anubis.distributed.kill_switch import KillSwitchController, KillSwitchStatus, KillTrigger


class SOCResponseRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SOCResponseActionType(StrEnum):
    LOG_ONLY = "log_only"
    THROTTLE_AGENT = "throttle_agent"
    INCREASE_MONITORING = "increase_monitoring"
    PAUSE_TASK = "pause_task_execution"
    ISOLATE_SANDBOX = "isolate_sandbox"
    TRIGGER_KILL_SWITCH = "trigger_kill_switch"
    FREEZE_SYSTEM_STATE = "freeze_system_state"
    RELEASE_AGENT = "release_agent"
    RESUME_TASK = "resume_task"
    RELEASE_SANDBOX = "release_sandbox"


class MitigationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    COMPLETED = "completed"


@dataclass(frozen=True)
class MitigationAction:
    action_id: str
    action_type: SOCResponseActionType
    status: MitigationStatus
    task_id: str
    agent_id: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class MitigationPlan:
    risk_level: SOCResponseRiskLevel
    score: RiskScore
    task_id: str
    agent_id: str
    action_types: tuple[SOCResponseActionType, ...]
    findings: tuple[AnomalyFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "score": int(self.score),
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action_types": [action.value for action in self.action_types],
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class EnforcementState:
    throttled_agents: tuple[str, ...] = ()
    monitored_agents: tuple[str, ...] = ()
    paused_tasks: tuple[str, ...] = ()
    isolated_sandboxes: tuple[str, ...] = ()
    actions: tuple[MitigationAction, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "throttled_agents": list(self.throttled_agents),
            "monitored_agents": list(self.monitored_agents),
            "paused_tasks": list(self.paused_tasks),
            "isolated_sandboxes": list(self.isolated_sandboxes),
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class SOCResponseResult:
    plan: MitigationPlan
    actions: tuple[MitigationAction, ...]
    kill_switch_status: KillSwitchStatus | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
            "kill_switch_status": self.kill_switch_status.to_dict() if self.kill_switch_status else None,
        }


class EnforcementController:
    """Applies and tracks reversible SOC enforcement actions."""

    def __init__(self) -> None:
        self._throttled_agents: set[str] = set()
        self._monitored_agents: set[str] = set()
        self._paused_tasks: set[str] = set()
        self._isolated_sandboxes: set[str] = set()
        self._actions: list[MitigationAction] = []
        self._lock = RLock()

    def apply(self, action_type: SOCResponseActionType, *, task_id: str, agent_id: str, reason: str, metadata: dict[str, Any] | None = None) -> MitigationAction:
        metadata = dict(metadata or {})
        with self._lock:
            if action_type == SOCResponseActionType.THROTTLE_AGENT:
                self._throttled_agents.add(agent_id)
                status = MitigationStatus.ACTIVE
            elif action_type == SOCResponseActionType.INCREASE_MONITORING:
                self._monitored_agents.add(agent_id)
                status = MitigationStatus.ACTIVE
            elif action_type == SOCResponseActionType.PAUSE_TASK:
                self._paused_tasks.add(task_id)
                status = MitigationStatus.ACTIVE
            elif action_type == SOCResponseActionType.ISOLATE_SANDBOX:
                self._isolated_sandboxes.add(_sandbox_id(task_id, metadata))
                status = MitigationStatus.ACTIVE
            elif action_type in {SOCResponseActionType.TRIGGER_KILL_SWITCH, SOCResponseActionType.FREEZE_SYSTEM_STATE, SOCResponseActionType.LOG_ONLY}:
                status = MitigationStatus.COMPLETED
            elif action_type == SOCResponseActionType.RELEASE_AGENT:
                self._throttled_agents.discard(agent_id)
                self._monitored_agents.discard(agent_id)
                status = MitigationStatus.RELEASED
            elif action_type == SOCResponseActionType.RESUME_TASK:
                self._paused_tasks.discard(task_id)
                status = MitigationStatus.RELEASED
            elif action_type == SOCResponseActionType.RELEASE_SANDBOX:
                self._isolated_sandboxes.discard(_sandbox_id(task_id, metadata))
                status = MitigationStatus.RELEASED
            else:  # pragma: no cover - enum exhaustiveness guard
                raise ValueError(f"unsupported action type: {action_type}")

            action = MitigationAction(
                action_id=f"mitigation_{uuid4().hex}",
                action_type=action_type,
                status=status,
                task_id=task_id,
                agent_id=agent_id,
                reason=reason,
                metadata=metadata,
            )
            self._actions.append(action)
            return action

    def release_agent(self, agent_id: str, *, task_id: str = "global", reason: str = "agent cleared for normal execution") -> MitigationAction:
        return self.apply(SOCResponseActionType.RELEASE_AGENT, task_id=task_id, agent_id=agent_id, reason=reason)

    def resume_task(self, task_id: str, *, agent_id: str = "soc-response", reason: str = "task cleared for execution") -> MitigationAction:
        return self.apply(SOCResponseActionType.RESUME_TASK, task_id=task_id, agent_id=agent_id, reason=reason)

    def release_sandbox(self, sandbox_id: str, *, task_id: str = "global", agent_id: str = "soc-response", reason: str = "sandbox cleared") -> MitigationAction:
        return self.apply(SOCResponseActionType.RELEASE_SANDBOX, task_id=task_id, agent_id=agent_id, reason=reason, metadata={"sandbox_id": sandbox_id})

    def is_agent_throttled(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._throttled_agents

    def is_task_paused(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._paused_tasks

    def is_sandbox_isolated(self, sandbox_id: str) -> bool:
        with self._lock:
            return sandbox_id in self._isolated_sandboxes

    def state(self) -> EnforcementState:
        with self._lock:
            return EnforcementState(
                throttled_agents=tuple(sorted(self._throttled_agents)),
                monitored_agents=tuple(sorted(self._monitored_agents)),
                paused_tasks=tuple(sorted(self._paused_tasks)),
                isolated_sandboxes=tuple(sorted(self._isolated_sandboxes)),
                actions=tuple(self._actions),
            )


class MitigationSystem:
    """Maps anomaly risk to deterministic mitigation plans."""

    def plan(self, classification: RiskClassification) -> MitigationPlan:
        risk_level = _risk_level(classification.score)
        if risk_level == SOCResponseRiskLevel.LOW:
            actions = (SOCResponseActionType.LOG_ONLY,)
        elif risk_level == SOCResponseRiskLevel.MEDIUM:
            actions = (SOCResponseActionType.THROTTLE_AGENT, SOCResponseActionType.INCREASE_MONITORING)
        elif risk_level == SOCResponseRiskLevel.HIGH:
            actions = (SOCResponseActionType.PAUSE_TASK, SOCResponseActionType.ISOLATE_SANDBOX)
        else:
            actions = (SOCResponseActionType.TRIGGER_KILL_SWITCH, SOCResponseActionType.FREEZE_SYSTEM_STATE)
        return MitigationPlan(
            risk_level=risk_level,
            score=classification.score,
            task_id=classification.event.task_id,
            agent_id=classification.event.agent_id,
            action_types=actions,
            findings=classification.findings,
        )


class SOCResponseEngine:
    """Real-time SOC response engine for anomaly classifications."""

    def __init__(
        self,
        *,
        enforcement: EnforcementController | None = None,
        mitigation: MitigationSystem | None = None,
        kill_switch: KillSwitchController | None = None,
    ) -> None:
        self.enforcement = enforcement or EnforcementController()
        self.mitigation = mitigation or MitigationSystem()
        self.kill_switch = kill_switch or KillSwitchController()
        self._results: list[SOCResponseResult] = []
        self._lock = RLock()

    def respond(self, classification: RiskClassification) -> SOCResponseResult:
        plan = self.mitigation.plan(classification)
        actions: list[MitigationAction] = []
        kill_status: KillSwitchStatus | None = None
        metadata = _metadata_for(classification)
        reason = _reason_for(classification)

        for action_type in plan.action_types:
            action = self.enforcement.apply(
                action_type,
                task_id=plan.task_id,
                agent_id=plan.agent_id,
                reason=reason,
                metadata=metadata,
            )
            actions.append(action)
            if action_type == SOCResponseActionType.TRIGGER_KILL_SWITCH:
                kill_status = self.kill_switch.trigger(
                    KillTrigger.SYSTEM_INSTABILITY,
                    reason,
                    source="soc-response-engine",
                    metadata={"classification": classification.to_dict(), "mitigation_action": action.to_dict()},
                    frozen_state={"soc_response": {"plan": plan.to_dict(), "actions": [item.to_dict() for item in actions]}},
                )

        result = SOCResponseResult(plan=plan, actions=tuple(actions), kill_switch_status=kill_status)
        with self._lock:
            self._results.append(result)
        return result

    def respond_many(self, classifications: tuple[RiskClassification, ...] | list[RiskClassification]) -> tuple[SOCResponseResult, ...]:
        return tuple(self.respond(classification) for classification in classifications)

    def ingest(self, classification: RiskClassification) -> None:
        """Streaming sink for anomaly classifications."""
        self.respond(classification)

    def release_agent(self, agent_id: str) -> MitigationAction:
        return self.enforcement.release_agent(agent_id)

    def resume_task(self, task_id: str) -> MitigationAction:
        return self.enforcement.resume_task(task_id)

    def release_sandbox(self, sandbox_id: str) -> MitigationAction:
        return self.enforcement.release_sandbox(sandbox_id)

    def results(self) -> tuple[SOCResponseResult, ...]:
        with self._lock:
            return tuple(self._results)


def _risk_level(score: RiskScore) -> SOCResponseRiskLevel:
    if score == RiskScore.SAFE:
        return SOCResponseRiskLevel.LOW
    if score == RiskScore.SUSPICIOUS:
        return SOCResponseRiskLevel.MEDIUM
    if score == RiskScore.DANGEROUS:
        return SOCResponseRiskLevel.HIGH
    return SOCResponseRiskLevel.CRITICAL


def _metadata_for(classification: RiskClassification) -> dict[str, Any]:
    event_payload = dict(classification.event.payload)
    sandbox_id = event_payload.get("sandbox_id") or event_payload.get("sandbox") or classification.event.task_id
    return {
        "score": int(classification.score),
        "event_type": classification.event.event_type,
        "sandbox_id": sandbox_id,
        "findings": [finding.to_dict() for finding in classification.findings],
    }


def _reason_for(classification: RiskClassification) -> str:
    if classification.findings:
        return "; ".join(finding.reason for finding in classification.findings)
    return "no anomaly detected"


def _sandbox_id(task_id: str, metadata: dict[str, Any]) -> str:
    value = metadata.get("sandbox_id") or metadata.get("sandbox") or task_id
    return str(value)


__all__ = [
    "EnforcementController",
    "EnforcementState",
    "MitigationAction",
    "MitigationPlan",
    "MitigationStatus",
    "MitigationSystem",
    "SOCResponseActionType",
    "SOCResponseEngine",
    "SOCResponseResult",
    "SOCResponseRiskLevel",
]
