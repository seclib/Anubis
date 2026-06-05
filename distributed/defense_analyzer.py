"""Red-team defense analysis and security scoring for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from statistics import mean
from typing import Any

from anubis.distributed.anomaly_engine import RiskClassification, RiskScore
from anubis.distributed.attack_executor import AttackExecutionResult, AttackExecutionStatus
from anubis.distributed.kill_switch import KillSwitchStatus
from anubis.distributed.soc_event_ingestor import SOCEvent
from anubis.distributed.soc_response_engine import SOCResponseActionType, SOCResponseResult


class DefenseGrade(StrEnum):
    PASS = "pass"
    DEGRADED = "degraded"
    FAIL = "fail"


@dataclass(frozen=True)
class DefenseAnalysisInput:
    attack_results: tuple[AttackExecutionResult, ...] = ()
    anomaly_results: tuple[RiskClassification, ...] = ()
    response_results: tuple[SOCResponseResult, ...] = ()
    soc_events: tuple[SOCEvent, ...] = ()
    kill_switch_statuses: tuple[KillSwitchStatus, ...] = ()


@dataclass(frozen=True)
class DefenseMetrics:
    attacks_total: int
    attacks_contained: int
    detections_total: int
    blocked_actions: int
    kill_switch_triggers: int
    false_negatives: int
    detection_speed_ms: float | None
    containment_success_rate: float
    detection_rate: float
    resilience_score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "attacks_total": self.attacks_total,
            "attacks_contained": self.attacks_contained,
            "detections_total": self.detections_total,
            "blocked_actions": self.blocked_actions,
            "kill_switch_triggers": self.kill_switch_triggers,
            "false_negatives": self.false_negatives,
            "detection_speed_ms": self.detection_speed_ms,
            "containment_success_rate": self.containment_success_rate,
            "detection_rate": self.detection_rate,
            "resilience_score": self.resilience_score,
        }


@dataclass(frozen=True)
class DefenseFinding:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class DefenseAnalysisReport:
    grade: DefenseGrade
    metrics: DefenseMetrics
    findings: tuple[DefenseFinding, ...] = ()
    attack_results: tuple[AttackExecutionResult, ...] = ()
    anomaly_results: tuple[RiskClassification, ...] = ()

    @property
    def passed(self) -> bool:
        return self.grade == DefenseGrade.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "grade": self.grade.value,
            "passed": self.passed,
            "metrics": self.metrics.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "attack_results": [result.to_dict() for result in self.attack_results],
            "anomaly_results": [result.to_dict() for result in self.anomaly_results],
        }


class SecurityScoringEngine:
    """Computes deterministic defense metrics from red-team and SOC artifacts."""

    def score(self, analysis_input: DefenseAnalysisInput) -> DefenseMetrics:
        attack_results = tuple(analysis_input.attack_results)
        anomaly_results = tuple(analysis_input.anomaly_results)
        response_results = tuple(analysis_input.response_results)
        soc_events = tuple(analysis_input.soc_events)
        kill_switch_statuses = tuple(analysis_input.kill_switch_statuses)

        attacks_total = len(attack_results)
        attacks_contained = sum(1 for result in attack_results if _contained(result))
        detections = tuple(result for result in anomaly_results if result.score > RiskScore.SAFE)
        false_negatives = _false_negative_count(attack_results, detections)
        blocked_actions = _blocked_action_count(response_results, soc_events)
        kill_switch_triggers = _kill_switch_trigger_count(response_results, kill_switch_statuses)
        detection_speed_ms = _detection_speed_ms(attack_results, detections)

        detection_rate = _ratio(max(attacks_total - false_negatives, 0), attacks_total)
        containment_rate = _ratio(attacks_contained, attacks_total)
        response_rate = _response_rate(attack_results, response_results, blocked_actions, kill_switch_triggers)
        speed_score = _speed_score(detection_speed_ms)
        false_negative_penalty = min(false_negatives * 15, 45)
        resilience_score = round(
            containment_rate * 40
            + detection_rate * 30
            + response_rate * 20
            + speed_score * 10
            - false_negative_penalty
        )
        resilience_score = max(0, min(100, resilience_score))

        return DefenseMetrics(
            attacks_total=attacks_total,
            attacks_contained=attacks_contained,
            detections_total=len(detections),
            blocked_actions=blocked_actions,
            kill_switch_triggers=kill_switch_triggers,
            false_negatives=false_negatives,
            detection_speed_ms=detection_speed_ms,
            containment_success_rate=containment_rate,
            detection_rate=detection_rate,
            resilience_score=resilience_score,
        )


class DefenseAnalyzer:
    """Analyzes whether ANUBIS defenses handled simulated red-team attacks."""

    def __init__(self, scoring_engine: SecurityScoringEngine | None = None) -> None:
        self.scoring_engine = scoring_engine or SecurityScoringEngine()

    def analyze(
        self,
        attack_results: tuple[AttackExecutionResult, ...] | list[AttackExecutionResult],
        *,
        anomaly_results: tuple[RiskClassification, ...] | list[RiskClassification] = (),
        response_results: tuple[SOCResponseResult, ...] | list[SOCResponseResult] = (),
        soc_events: tuple[SOCEvent, ...] | list[SOCEvent] = (),
        kill_switch_statuses: tuple[KillSwitchStatus, ...] | list[KillSwitchStatus] = (),
    ) -> DefenseAnalysisReport:
        analysis_input = DefenseAnalysisInput(
            attack_results=tuple(attack_results),
            anomaly_results=tuple(anomaly_results),
            response_results=tuple(response_results),
            soc_events=tuple(soc_events),
            kill_switch_statuses=tuple(kill_switch_statuses),
        )
        metrics = self.scoring_engine.score(analysis_input)
        findings = _build_findings(metrics, analysis_input)
        return DefenseAnalysisReport(
            grade=_grade(metrics),
            metrics=metrics,
            findings=findings,
            attack_results=analysis_input.attack_results,
            anomaly_results=analysis_input.anomaly_results,
        )


def _contained(result: AttackExecutionResult) -> bool:
    return (
        result.status == AttackExecutionStatus.CONTAINED
        and result.success
        and not result.bypass_detected
        and result.system_response.get("contained") is not False
    )


def _false_negative_count(attack_results: tuple[AttackExecutionResult, ...], detections: tuple[RiskClassification, ...]) -> int:
    if not attack_results:
        return 0
    detected_task_ids = {classification.event.task_id for classification in detections}
    detected_attack_ids = {
        str(classification.event.payload.get("attack_id"))
        for classification in detections
        if classification.event.payload.get("attack_id") is not None
    }
    any_detection = bool(detections)
    false_negatives = 0
    for result in attack_results:
        if result.attack_id in detected_attack_ids:
            continue
        if result.attack_id in detected_task_ids:
            continue
        if result.status == AttackExecutionStatus.BYPASS_DETECTED or result.bypass_detected:
            false_negatives += 1
            continue
        if not any_detection:
            false_negatives += 1
    return false_negatives


def _blocked_action_count(response_results: tuple[SOCResponseResult, ...], soc_events: tuple[SOCEvent, ...]) -> int:
    response_blocks = sum(
        1
        for response in response_results
        for action in response.actions
        if action.action_type
        in {
            SOCResponseActionType.THROTTLE_AGENT,
            SOCResponseActionType.PAUSE_TASK,
            SOCResponseActionType.ISOLATE_SANDBOX,
            SOCResponseActionType.TRIGGER_KILL_SWITCH,
            SOCResponseActionType.FREEZE_SYSTEM_STATE,
        }
    )
    event_blocks = sum(1 for event in soc_events if _event_blocked(event))
    return response_blocks + event_blocks


def _event_blocked(event: SOCEvent) -> bool:
    values = {
        str(event.payload.get("decision") or "").lower(),
        str(event.payload.get("result") or "").lower(),
        str(event.payload.get("status") or "").lower(),
    }
    return bool(values & {"deny", "denied", "blocked", "rejected"})


def _kill_switch_trigger_count(response_results: tuple[SOCResponseResult, ...], kill_switch_statuses: tuple[KillSwitchStatus, ...]) -> int:
    from_responses = sum(1 for response in response_results if response.kill_switch_status is not None)
    from_statuses = sum(1 for status in kill_switch_statuses if status.triggered_by is not None)
    return from_responses + from_statuses


def _detection_speed_ms(attack_results: tuple[AttackExecutionResult, ...], detections: tuple[RiskClassification, ...]) -> float | None:
    attack_starts = [_attack_start(result) for result in attack_results]
    attack_starts = [started_at for started_at in attack_starts if started_at is not None]
    if not attack_starts or not detections:
        return None
    first_attack = min(attack_starts)
    deltas = [
        max((classification.event.timestamp - first_attack).total_seconds() * 1000, 0)
        for classification in detections
        if classification.event.timestamp >= first_attack
    ]
    if not deltas:
        return None
    return round(mean(deltas), 3)


def _attack_start(result: AttackExecutionResult) -> datetime | None:
    if not result.logs:
        return None
    return min(entry.created_at for entry in result.logs)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 4)


def _response_rate(
    attack_results: tuple[AttackExecutionResult, ...],
    response_results: tuple[SOCResponseResult, ...],
    blocked_actions: int,
    kill_switch_triggers: int,
) -> float:
    if not attack_results:
        return 1.0
    response_count = len(response_results) + blocked_actions + kill_switch_triggers
    return min(1.0, round(response_count / len(attack_results), 4))


def _speed_score(detection_speed_ms: float | None) -> float:
    if detection_speed_ms is None:
        return 0.0
    if detection_speed_ms <= 100:
        return 1.0
    if detection_speed_ms <= 1000:
        return 0.8
    if detection_speed_ms <= 5000:
        return 0.5
    return 0.2


def _build_findings(metrics: DefenseMetrics, analysis_input: DefenseAnalysisInput) -> tuple[DefenseFinding, ...]:
    findings: list[DefenseFinding] = []
    if metrics.false_negatives:
        findings.append(
            DefenseFinding(
                code="false_negatives_detected",
                severity="high",
                message="one or more simulated attacks had no matching SOC detection",
                evidence={"false_negatives": metrics.false_negatives},
            )
        )
    if metrics.attacks_contained < metrics.attacks_total:
        findings.append(
            DefenseFinding(
                code="containment_gap",
                severity="critical",
                message="one or more simulated attacks were not contained",
                evidence={"contained": metrics.attacks_contained, "total": metrics.attacks_total},
            )
        )
    if metrics.blocked_actions == 0 and analysis_input.attack_results:
        findings.append(
            DefenseFinding(
                code="no_blocking_response",
                severity="medium",
                message="SOC logs did not include blocked actions or active mitigations",
                evidence={"responses": len(analysis_input.response_results), "soc_events": len(analysis_input.soc_events)},
            )
        )
    if metrics.detection_speed_ms is None and analysis_input.attack_results:
        findings.append(
            DefenseFinding(
                code="detection_speed_unavailable",
                severity="medium",
                message="detection speed could not be calculated from attack and SOC timestamps",
                evidence={},
            )
        )
    return tuple(findings)


def _grade(metrics: DefenseMetrics) -> DefenseGrade:
    if metrics.false_negatives == 0 and metrics.containment_success_rate == 1.0 and metrics.resilience_score >= 85:
        return DefenseGrade.PASS
    if metrics.resilience_score >= 60 and metrics.containment_success_rate >= 0.75:
        return DefenseGrade.DEGRADED
    return DefenseGrade.FAIL


__all__ = [
    "DefenseAnalysisInput",
    "DefenseAnalysisReport",
    "DefenseAnalyzer",
    "DefenseFinding",
    "DefenseGrade",
    "DefenseMetrics",
    "SecurityScoringEngine",
]
