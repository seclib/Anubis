from __future__ import annotations

import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import re
from pathlib import Path
from typing import Any, AsyncIterator, Protocol


class ThreatClass(str, Enum):
    RECONNAISSANCE = "reconnaissance"
    AUTH_ABUSE = "auth_abuse"
    INJECTION_ATTEMPT = "injection_attempt"
    PRIVILEGE_RISK = "privilege_risk"
    NETWORK_ANOMALY = "network_anomaly"
    MALWARE_SIGNAL = "malware_signal"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class LogEvent:
    timestamp: str
    source: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryHit:
    source: str
    namespace: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Detection:
    detection_id: str
    timestamp: str
    threat_class: ThreatClass
    severity: AlertSeverity
    confidence: float
    summary: str
    evidence: tuple[LogEvent, ...]
    memory: tuple[MemoryHit, ...]


@dataclass(frozen=True)
class IncidentReport:
    incident_id: str
    created_at: str
    severity: AlertSeverity
    title: str
    summary: str
    detections: tuple[Detection, ...]
    evidence: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    references: tuple[str, ...]


@dataclass(frozen=True)
class Alert:
    alert_id: str
    created_at: str
    severity: AlertSeverity
    title: str
    body: str
    incident_id: str
    delivered: bool = False


class QdrantLike(Protocol):
    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        ...


class DefenseModeGuard:
    BLOCKED = ("attack", "exploit", "shell", "subprocess", "socket", "requests", "connect(", "send(", "exec(", "eval(")

    def assert_defensive(self, intent: str) -> None:
        lowered = intent.lower()
        if any(token in lowered for token in self.BLOCKED):
            raise RuntimeError("defense mode blocks offensive or external execution intent")


class ObsidianRetriever:
    def __init__(self, vault_path: Path = Path("vault"), namespaces: tuple[str, ...] = ("skills", "memory", "incidents")) -> None:
        self.vault_path = vault_path
        self.namespaces = namespaces

    async def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        terms = _terms(query)
        hits: list[MemoryHit] = []
        for namespace in self.namespaces:
            root = _inside(self.vault_path, Path(namespace))
            if not root.exists():
                continue
            for path in root.rglob("*.md"):
                text = await asyncio.to_thread(path.read_text, encoding="utf-8")
                score = _score_terms(terms, text)
                if score:
                    hits.append(MemoryHit("obsidian", namespace, score, text[:1200], {"path": path.relative_to(self.vault_path).as_posix()}))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


class QdrantRetriever:
    def __init__(self, store: QdrantLike | None = None, namespace: str = "security") -> None:
        self.store = store
        self.namespace = namespace

    async def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        if self.store is None:
            return []
        rows = await asyncio.to_thread(self.store.search, query, limit)
        return [
            MemoryHit("qdrant", self.namespace, float(row.get("score", 0.0)), str(row.get("text") or row.get("content") or ""), row)
            for row in rows
        ]


class RagMemory:
    def __init__(self, obsidian: ObsidianRetriever | None = None, qdrant: QdrantRetriever | None = None) -> None:
        self.obsidian = obsidian or ObsidianRetriever()
        self.qdrant = qdrant or QdrantRetriever()

    async def retrieve(self, query: str, limit: int = 8) -> tuple[MemoryHit, ...]:
        obsidian_hits, qdrant_hits = await asyncio.gather(self.obsidian.search(query, limit), self.qdrant.search(query, limit))
        hits = [*obsidian_hits, *qdrant_hits]
        return tuple(sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit])


class AsyncLogSource:
    def __init__(self, paths: tuple[Path, ...] = (Path("logs/anubis.log"),), poll_seconds: float = 1.0) -> None:
        self.paths = paths
        self.poll_seconds = poll_seconds
        self.offsets: dict[Path, int] = {}

    async def stream(self) -> AsyncIterator[LogEvent]:
        while True:
            emitted = False
            for path in self.paths:
                if not path.exists():
                    continue
                offset = self.offsets.get(path, 0)
                size = path.stat().st_size
                if size < offset:
                    offset = 0
                if size == offset:
                    continue
                lines, new_offset = await asyncio.to_thread(self._read_new, path, offset)
                self.offsets[path] = new_offset
                for line in lines:
                    emitted = True
                    yield self._parse(path, line)
            if not emitted:
                await asyncio.sleep(self.poll_seconds)

    def _read_new(self, path: Path, offset: int) -> tuple[list[str], int]:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            lines = [line.strip() for line in handle if line.strip()]
            return lines, handle.tell()

    def _parse(self, path: Path, line: str) -> LogEvent:
        fields = dict(re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)=([^ ]+)", line))
        timestamp = fields.get("timestamp") or datetime.now(UTC).isoformat()
        return LogEvent(timestamp, path.as_posix(), line, fields)


class AnomalyDetector:
    KEYWORDS = {
        ThreatClass.RECONNAISSANCE: ("scan", "sweep", "probe", "banner", "port"),
        ThreatClass.AUTH_ABUSE: ("failed", "invalid", "password", "brute", "lockout", "login"),
        ThreatClass.INJECTION_ATTEMPT: ("injection", "payload", "sql", "template", "../", "%27", "union"),
        ThreatClass.PRIVILEGE_RISK: ("sudo", "privilege", "token", "admin", "escalation", "permission"),
        ThreatClass.NETWORK_ANOMALY: ("beacon", "egress", "dns", "rare", "spike", "anomaly"),
        ThreatClass.MALWARE_SIGNAL: ("malware", "persistence", "dropper", "c2", "ransom", "trojan"),
    }

    def __init__(self, window_size: int = 200) -> None:
        self.window: deque[LogEvent] = deque(maxlen=window_size)
        self.source_counts: Counter[str] = Counter()

    def inspect(self, event: LogEvent) -> tuple[ThreatClass, float, str]:
        self.window.append(event)
        text = event.message.lower()
        scores = {
            threat: sum(1 for keyword in keywords if keyword in text)
            for threat, keywords in self.KEYWORDS.items()
        }
        threat, score = max(scores.items(), key=lambda item: item[1])
        source_key = str(event.fields.get("src") or event.fields.get("source") or event.source)
        self.source_counts[source_key] += 1
        burst = self.source_counts[source_key] / max(1, len(self.window))
        confidence = min(1.0, score * 0.22 + burst * 0.7)
        if score == 0 and burst < 0.18:
            return ThreatClass.UNKNOWN, 0.0, "no anomaly detected"
        reason = f"matched {score} threat indicators; source burst ratio {burst:.2f}"
        return threat if score else ThreatClass.NETWORK_ANOMALY, round(confidence, 3), reason


class ThreatClassifier:
    def classify(self, threat: ThreatClass, confidence: float, event: LogEvent, memory: tuple[MemoryHit, ...]) -> tuple[AlertSeverity, str]:
        memory_boost = min(0.25, sum(hit.score for hit in memory[:3]) / 10)
        score = min(1.0, confidence + memory_boost)
        if threat == ThreatClass.UNKNOWN:
            return AlertSeverity.INFO, "unclassified low-confidence event"
        if score >= 0.85:
            severity = AlertSeverity.CRITICAL
        elif score >= 0.7:
            severity = AlertSeverity.HIGH
        elif score >= 0.45:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW
        return severity, f"{threat.value} classified from defensive telemetry"


class IncidentReporter:
    ACTIONS = {
        ThreatClass.RECONNAISSANCE: ("review exposed services", "validate IDS coverage", "confirm source reputation internally"),
        ThreatClass.AUTH_ABUSE: ("review authentication logs", "validate lockout policy", "rotate affected credentials if confirmed"),
        ThreatClass.INJECTION_ATTEMPT: ("review web request context", "validate input filtering", "preserve application logs"),
        ThreatClass.PRIVILEGE_RISK: ("review permission changes", "validate least privilege", "isolate affected identity if confirmed"),
        ThreatClass.NETWORK_ANOMALY: ("review egress baseline", "inspect DNS telemetry", "preserve flow logs"),
        ThreatClass.MALWARE_SIGNAL: ("isolate suspected host defensively", "collect forensic timeline", "review persistence indicators"),
        ThreatClass.UNKNOWN: ("continue monitoring", "collect additional context", "review detection rules"),
    }

    def create(self, detections: tuple[Detection, ...]) -> IncidentReport:
        top = max(detections, key=lambda detection: _severity_rank(detection.severity))
        incident_id = "INC-" + hashlib.sha256("|".join(d.detection_id for d in detections).encode("utf-8")).hexdigest()[:12]
        evidence = tuple(event.message for detection in detections for event in detection.evidence[:3])
        refs = tuple(hit.metadata.get("path", hit.namespace) for detection in detections for hit in detection.memory[:2])
        return IncidentReport(
            incident_id,
            datetime.now(UTC).isoformat(),
            top.severity,
            f"{top.threat_class.value.replace('_', ' ').title()} Detected",
            top.summary,
            detections,
            evidence,
            self.ACTIONS[top.threat_class],
            refs,
        )


class AlertManager:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    async def publish(self, report: IncidentReport) -> Alert:
        alert = Alert(
            "ALERT-" + report.incident_id.removeprefix("INC-"),
            datetime.now(UTC).isoformat(),
            report.severity,
            report.title,
            report.summary,
            report.incident_id,
            True,
        )
        self.alerts.append(alert)
        return alert


class CybersecurityAnalystAgent:
    def __init__(
        self,
        logs: AsyncLogSource | None = None,
        memory: RagMemory | None = None,
        detector: AnomalyDetector | None = None,
        classifier: ThreatClassifier | None = None,
        reporter: IncidentReporter | None = None,
        alerts: AlertManager | None = None,
        guard: DefenseModeGuard | None = None,
        min_confidence: float = 0.35,
    ) -> None:
        self.logs = logs or AsyncLogSource()
        self.memory = memory or RagMemory()
        self.detector = detector or AnomalyDetector()
        self.classifier = classifier or ThreatClassifier()
        self.reporter = reporter or IncidentReporter()
        self.alerts = alerts or AlertManager()
        self.guard = guard or DefenseModeGuard()
        self.min_confidence = min_confidence
        self.running = False

    async def run(self) -> AsyncIterator[Alert]:
        self.guard.assert_defensive("continuous defensive monitoring and incident reporting")
        self.running = True
        async for event in self.logs.stream():
            if not self.running:
                break
            alert = await self.analyze(event)
            if alert:
                yield alert

    async def analyze(self, event: LogEvent) -> Alert | None:
        threat, confidence, reason = self.detector.inspect(event)
        if confidence < self.min_confidence:
            return None
        query = f"{threat.value} {event.message}"
        memory = await self.memory.retrieve(query)
        severity, summary = self.classifier.classify(threat, confidence, event, memory)
        detection = Detection(
            self._detection_id(event, threat),
            datetime.now(UTC).isoformat(),
            threat,
            severity,
            confidence,
            f"{summary}; {reason}",
            (event,),
            memory,
        )
        report = self.reporter.create((detection,))
        return await self.alerts.publish(report)

    def stop(self) -> None:
        self.running = False

    def _detection_id(self, event: LogEvent, threat: ThreatClass) -> str:
        raw = f"{event.timestamp}|{event.source}|{event.message}|{threat.value}"
        return "DET-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)}


def _score_terms(terms: set[str], text: str) -> float:
    if not terms:
        return 0.0
    haystack = text.lower()
    return round(sum(1 for term in terms if term in haystack) / len(terms), 3)


def _severity_rank(severity: AlertSeverity) -> int:
    return {
        AlertSeverity.INFO: 0,
        AlertSeverity.LOW: 1,
        AlertSeverity.MEDIUM: 2,
        AlertSeverity.HIGH: 3,
        AlertSeverity.CRITICAL: 4,
    }[severity]


def _inside(base: Path, candidate: Path) -> Path:
    root = base.resolve()
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("path escapes Obsidian vault")
    return resolved
