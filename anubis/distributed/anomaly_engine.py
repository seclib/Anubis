"""AI SOC anomaly detection and behavior scoring for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from threading import RLock
from typing import Any
from urllib.parse import urlparse

from anubis.distributed.soc_event_ingestor import SOCEvent, SOCEventType


class RiskScore(IntEnum):
    SAFE = 0
    SUSPICIOUS = 1
    DANGEROUS = 2
    CRITICAL = 3


class AnomalyCategory(StrEnum):
    EXECUTION = "execution"
    FILE = "file"
    BEHAVIOR = "behavior"
    NETWORK = "network"


class AnomalyCode(StrEnum):
    INFINITE_LOOP = "infinite_loop"
    REPEATED_FAILURES = "repeated_failures"
    UNEXPECTED_TOOL_USAGE = "unexpected_tool_usage"
    UNAUTHORIZED_PATH_ACCESS = "unauthorized_path_access"
    MASS_FILE_MODIFICATION = "mass_file_modification"
    PLANNER_EXECUTING = "planner_executing"
    EXECUTOR_PLANNING = "executor_planning"
    ROLE_VIOLATION = "role_violation"
    UNEXPECTED_EXTERNAL_CALL = "unexpected_external_call"
    FORBIDDEN_DOMAIN = "forbidden_domain"
    SYSTEM_ERROR = "system_error"


@dataclass(frozen=True)
class BehaviorBaseline:
    allowed_tools_by_role: dict[str, frozenset[str]] = field(default_factory=dict)
    allowed_event_types_by_role: dict[str, frozenset[str]] = field(default_factory=dict)
    allowlisted_domains: frozenset[str] = frozenset()
    forbidden_domains: frozenset[str] = frozenset({"localhost", "127.0.0.1", "0.0.0.0"})
    repeated_failure_threshold: int = 3
    repeated_action_threshold: int = 5
    mass_file_write_threshold: int = 10

    @classmethod
    def default(cls) -> "BehaviorBaseline":
        return cls(
            allowed_tools_by_role={
                "planner": frozenset({"read_file", "search_codebase"}),
                "executor": frozenset({"read_file", "write_file", "search_codebase", "run_command"}),
                "reviewer": frozenset({"read_file", "search_codebase"}),
            },
            allowed_event_types_by_role={
                "planner": frozenset({SOCEventType.AGENT_ACTION.value, SOCEventType.FILE_ACCESS.value, SOCEventType.ORCHESTRATION_EVENT.value}),
                "executor": frozenset(
                    {
                        SOCEventType.AGENT_ACTION.value,
                        SOCEventType.TOOL_EXECUTION.value,
                        SOCEventType.FILE_ACCESS.value,
                        SOCEventType.EXECUTION_STEP.value,
                        SOCEventType.ORCHESTRATION_EVENT.value,
                    }
                ),
                "reviewer": frozenset({SOCEventType.AGENT_ACTION.value, SOCEventType.FILE_ACCESS.value, SOCEventType.EXECUTION_STEP.value, SOCEventType.ORCHESTRATION_EVENT.value}),
            },
            allowlisted_domains=frozenset({"example.com"}),
        )


@dataclass(frozen=True)
class AnomalyFinding:
    task_id: str
    agent_id: str
    category: AnomalyCategory
    code: AnomalyCode
    score: RiskScore
    reason: str
    event: SOCEvent
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "category": self.category.value,
            "code": self.code.value,
            "score": int(self.score),
            "reason": self.reason,
            "event": self.event.to_dict(),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RiskClassification:
    event: SOCEvent
    score: RiskScore
    findings: tuple[AnomalyFinding, ...] = ()

    @property
    def safe(self) -> bool:
        return self.score == RiskScore.SAFE

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "score": int(self.score),
            "safe": self.safe,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class BehaviorScoringSystem:
    """Stateful risk scorer using role baselines and rolling event counters."""

    def __init__(self, baseline: BehaviorBaseline | None = None) -> None:
        self.baseline = baseline or BehaviorBaseline.default()
        self._failure_counts: dict[tuple[str, str], int] = {}
        self._action_counts: dict[tuple[str, str, str, str], int] = {}
        self._file_writes: dict[tuple[str, str], set[str]] = {}
        self._lock = RLock()

    def score(self, event: SOCEvent) -> RiskClassification:
        with self._lock:
            findings = [
                *self._score_behavior(event),
                *self._score_execution(event),
                *self._score_file(event),
                *self._score_network(event),
            ]
            score = max((finding.score for finding in findings), default=RiskScore.SAFE)
            return RiskClassification(event=event, score=score, findings=tuple(findings))

    def _score_behavior(self, event: SOCEvent) -> list[AnomalyFinding]:
        role = _role_from_agent(event.agent_id)
        findings: list[AnomalyFinding] = []
        if role is None:
            return findings

        allowed_event_types = self.baseline.allowed_event_types_by_role.get(role, frozenset())
        if allowed_event_types and event.event_type not in allowed_event_types:
            findings.append(
                _finding(
                    event,
                    AnomalyCategory.BEHAVIOR,
                    AnomalyCode.ROLE_VIOLATION,
                    RiskScore.SUSPICIOUS,
                    f"{role} emitted unexpected event type {event.event_type}",
                    {"role": role, "allowed_event_types": sorted(allowed_event_types)},
                )
            )

        action = _action_text(event)
        if role == "planner" and _looks_like_execution(event, action):
            findings.append(
                _finding(event, AnomalyCategory.BEHAVIOR, AnomalyCode.PLANNER_EXECUTING, RiskScore.CRITICAL, "planner attempted execution behavior", {"action": action})
            )
        if role == "executor" and _looks_like_planning(event, action):
            findings.append(
                _finding(event, AnomalyCategory.BEHAVIOR, AnomalyCode.EXECUTOR_PLANNING, RiskScore.DANGEROUS, "executor attempted planning behavior", {"action": action})
            )

        tool = _tool_name(event)
        if tool:
            allowed_tools = self.baseline.allowed_tools_by_role.get(role, frozenset())
            if allowed_tools and tool not in allowed_tools:
                findings.append(
                    _finding(
                        event,
                        AnomalyCategory.EXECUTION,
                        AnomalyCode.UNEXPECTED_TOOL_USAGE,
                        RiskScore.DANGEROUS,
                        f"{role} used unexpected tool {tool}",
                        {"role": role, "tool": tool, "allowed_tools": sorted(allowed_tools)},
                    )
                )
        return findings

    def _score_execution(self, event: SOCEvent) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        failure = _is_failure(event)
        key = (event.task_id, event.agent_id)
        if failure:
            self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
            count = self._failure_counts[key]
            if count >= self.baseline.repeated_failure_threshold:
                findings.append(
                    _finding(
                        event,
                        AnomalyCategory.EXECUTION,
                        AnomalyCode.REPEATED_FAILURES,
                        RiskScore.DANGEROUS,
                        "agent crossed repeated failure threshold",
                        {"failures": count, "threshold": self.baseline.repeated_failure_threshold},
                    )
                )

        action = _action_text(event)
        action_key = (event.task_id, event.agent_id, event.event_type, action)
        self._action_counts[action_key] = self._action_counts.get(action_key, 0) + 1
        action_count = self._action_counts[action_key]
        if action_count >= self.baseline.repeated_action_threshold and event.event_type in {SOCEventType.TOOL_EXECUTION.value, SOCEventType.EXECUTION_STEP.value}:
            findings.append(
                _finding(
                    event,
                    AnomalyCategory.EXECUTION,
                    AnomalyCode.INFINITE_LOOP,
                    RiskScore.CRITICAL,
                    "same execution action repeated beyond loop threshold",
                    {"action": action, "count": action_count, "threshold": self.baseline.repeated_action_threshold},
                )
            )

        if event.event_type == SOCEventType.SYSTEM_ERROR.value:
            findings.append(_finding(event, AnomalyCategory.EXECUTION, AnomalyCode.SYSTEM_ERROR, RiskScore.SUSPICIOUS, "system error observed", dict(event.payload)))
        return findings

    def _score_file(self, event: SOCEvent) -> list[AnomalyFinding]:
        if event.event_type != SOCEventType.FILE_ACCESS.value:
            return []
        findings: list[AnomalyFinding] = []
        decision = str(event.payload.get("decision") or event.payload.get("result") or "").lower()
        path = str(event.payload.get("requested_path") or event.payload.get("path") or "")
        if decision in {"deny", "denied"} or _path_escape_attempt(path):
            findings.append(
                _finding(event, AnomalyCategory.FILE, AnomalyCode.UNAUTHORIZED_PATH_ACCESS, RiskScore.CRITICAL, "unauthorized path access attempt", {"path": path, "decision": decision})
            )

        action = str(event.payload.get("action") or event.payload.get("operation") or "").lower()
        if action == "write":
            key = (event.task_id, event.agent_id)
            self._file_writes.setdefault(key, set()).add(path)
            count = len(self._file_writes[key])
            if count >= self.baseline.mass_file_write_threshold:
                findings.append(
                    _finding(
                        event,
                        AnomalyCategory.FILE,
                        AnomalyCode.MASS_FILE_MODIFICATION,
                        RiskScore.DANGEROUS,
                        "mass file modification threshold crossed",
                        {"write_count": count, "threshold": self.baseline.mass_file_write_threshold},
                    )
                )
        return findings

    def _score_network(self, event: SOCEvent) -> list[AnomalyFinding]:
        if event.event_type != SOCEventType.NETWORK_REQUEST.value:
            return []
        host = _network_host(event)
        decision = str(event.payload.get("decision") or event.payload.get("result") or "").lower()
        findings: list[AnomalyFinding] = []
        if host in self.baseline.forbidden_domains or decision in {"deny", "denied"}:
            findings.append(
                _finding(event, AnomalyCategory.NETWORK, AnomalyCode.FORBIDDEN_DOMAIN, RiskScore.CRITICAL, "forbidden or denied network destination", {"host": host, "decision": decision})
            )
        elif host and self.baseline.allowlisted_domains and not _host_allowed(host, self.baseline.allowlisted_domains):
            findings.append(
                _finding(event, AnomalyCategory.NETWORK, AnomalyCode.UNEXPECTED_EXTERNAL_CALL, RiskScore.DANGEROUS, "network destination outside behavioral allowlist", {"host": host})
            )
        return findings


class RiskClassifier:
    """Classifies individual events or event streams into risk findings."""

    def __init__(self, scorer: BehaviorScoringSystem | None = None) -> None:
        self.scorer = scorer or BehaviorScoringSystem()

    def classify(self, event: SOCEvent) -> RiskClassification:
        return self.scorer.score(event)

    def classify_many(self, events: tuple[SOCEvent, ...] | list[SOCEvent]) -> tuple[RiskClassification, ...]:
        return tuple(self.classify(event) for event in events)


class AnomalyDetectionEngine:
    """SOC anomaly engine for streaming ANUBIS security telemetry."""

    def __init__(self, classifier: RiskClassifier | None = None) -> None:
        self.classifier = classifier or RiskClassifier()
        self._findings: list[AnomalyFinding] = []
        self._classifications: list[RiskClassification] = []
        self._lock = RLock()

    def analyze(self, event: SOCEvent) -> RiskClassification:
        classification = self.classifier.classify(event)
        with self._lock:
            self._classifications.append(classification)
            self._findings.extend(classification.findings)
        return classification

    def analyze_many(self, events: tuple[SOCEvent, ...] | list[SOCEvent]) -> tuple[RiskClassification, ...]:
        return tuple(self.analyze(event) for event in events)

    def findings(self, *, minimum_score: RiskScore | int = RiskScore.SUSPICIOUS) -> tuple[AnomalyFinding, ...]:
        threshold = RiskScore(minimum_score)
        with self._lock:
            return tuple(finding for finding in self._findings if finding.score >= threshold)

    def classifications(self) -> tuple[RiskClassification, ...]:
        with self._lock:
            return tuple(self._classifications)

    def ingest(self, event: SOCEvent) -> None:
        """Streaming pipeline sink compatible with SOCStreamingPipeline."""
        self.analyze(event)


def _finding(
    event: SOCEvent,
    category: AnomalyCategory,
    code: AnomalyCode,
    score: RiskScore,
    reason: str,
    evidence: dict[str, Any],
) -> AnomalyFinding:
    return AnomalyFinding(
        task_id=event.task_id,
        agent_id=event.agent_id,
        category=category,
        code=code,
        score=score,
        reason=reason,
        event=event,
        evidence=evidence,
    )


def _role_from_agent(agent_id: str) -> str | None:
    prefix = agent_id.split("-", 1)[0].strip().lower()
    return prefix if prefix in {"planner", "executor", "reviewer"} else None


def _tool_name(event: SOCEvent) -> str | None:
    tool = event.payload.get("tool") or event.payload.get("action")
    if event.event_type == SOCEventType.TOOL_EXECUTION.value and isinstance(tool, str):
        return tool
    return None


def _action_text(event: SOCEvent) -> str:
    return str(event.payload.get("action") or event.payload.get("decision") or event.payload.get("tool") or event.payload.get("message") or event.event_type).lower()


def _looks_like_execution(event: SOCEvent, action: str) -> bool:
    return event.event_type == SOCEventType.TOOL_EXECUTION.value or any(token in action for token in ("execute", "run_command", "write_file", "git_commit", "shell"))


def _looks_like_planning(event: SOCEvent, action: str) -> bool:
    return any(token in action for token in ("plan", "decompose", "dependency", "steps"))


def _is_failure(event: SOCEvent) -> bool:
    result = str(event.payload.get("result") or event.payload.get("status") or "").lower()
    success = event.payload.get("success")
    decision = str(event.payload.get("decision") or "").lower()
    return success is False or result in {"failure", "failed", "deny", "denied"} or decision in {"deny", "denied"}


def _path_escape_attempt(path: str) -> bool:
    return bool(path) and (path.startswith("/etc/") or path.startswith("/root/") or path.startswith("/home/") or "/../" in path or path.endswith("/..") or path.startswith("../"))


def _network_host(event: SOCEvent) -> str:
    host = str(event.payload.get("host") or "").strip().lower()
    if host:
        return host
    url = str(event.payload.get("url") or "")
    parsed = urlparse(url)
    return (parsed.hostname or "").strip().lower()


def _host_allowed(host: str, allowlist: frozenset[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)


__all__ = [
    "AnomalyCategory",
    "AnomalyCode",
    "AnomalyDetectionEngine",
    "AnomalyFinding",
    "BehaviorBaseline",
    "BehaviorScoringSystem",
    "RiskClassification",
    "RiskClassifier",
    "RiskScore",
]
