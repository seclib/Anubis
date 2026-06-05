"""Threat intelligence memory and learning loop for ANUBIS AI SOC."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from anubis.context.embeddings import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity
from anubis.distributed.anomaly_engine import AnomalyCode, BehaviorBaseline, RiskClassification, RiskScore
from anubis.distributed.soc_response_engine import SOCResponseResult


class IncidentVerdict(StrEnum):
    UNKNOWN = "unknown"
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    classification: RiskClassification
    response: SOCResponseResult | None = None
    verdict: IncidentVerdict = IncidentVerdict.UNKNOWN
    notes: str = ""
    pattern_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def task_id(self) -> str:
        return self.classification.event.task_id

    @property
    def agent_id(self) -> str:
        return self.classification.event.agent_id

    @property
    def score(self) -> RiskScore:
        return self.classification.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "classification": self.classification.to_dict(),
            "response": self.response.to_dict() if self.response else None,
            "verdict": self.verdict.value,
            "notes": self.notes,
            "pattern_text": self.pattern_text,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class SimilarIncident:
    incident: IncidentRecord
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"incident": self.incident.to_dict(), "score": self.score}


@dataclass(frozen=True)
class LearningAdjustment:
    field: str
    old_value: int
    new_value: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LearningFeedbackResult:
    baseline: BehaviorBaseline
    adjustments: tuple[LearningAdjustment, ...]
    false_positive_count: int
    true_positive_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": {
                "repeated_failure_threshold": self.baseline.repeated_failure_threshold,
                "repeated_action_threshold": self.baseline.repeated_action_threshold,
                "mass_file_write_threshold": self.baseline.mass_file_write_threshold,
                "allowlisted_domains": sorted(self.baseline.allowlisted_domains),
                "forbidden_domains": sorted(self.baseline.forbidden_domains),
            },
            "adjustments": [adjustment.to_dict() for adjustment in self.adjustments],
            "false_positive_count": self.false_positive_count,
            "true_positive_count": self.true_positive_count,
        }


class VectorMemory(Protocol):
    def upsert(self, incident_id: str, vector: tuple[float, ...], payload: dict[str, Any]) -> None: ...

    def search(self, vector: tuple[float, ...], *, limit: int = 5) -> tuple[tuple[str, float, dict[str, Any]], ...]: ...


class IncidentStore:
    """Thread-safe incident record storage."""

    def __init__(self) -> None:
        self._incidents: dict[str, IncidentRecord] = {}
        self._lock = RLock()

    def save(self, incident: IncidentRecord) -> IncidentRecord:
        with self._lock:
            self._incidents[incident.incident_id] = incident
            return incident

    def get(self, incident_id: str) -> IncidentRecord | None:
        with self._lock:
            return self._incidents.get(incident_id)

    def all(self) -> tuple[IncidentRecord, ...]:
        with self._lock:
            return tuple(sorted(self._incidents.values(), key=lambda item: item.created_at))

    def update_verdict(self, incident_id: str, verdict: IncidentVerdict, *, notes: str = "") -> IncidentRecord:
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                raise KeyError(f"incident not found: {incident_id}")
            updated = replace(incident, verdict=verdict, notes=notes or incident.notes, updated_at=datetime.now(timezone.utc))
            self._incidents[incident_id] = updated
            return updated


class InMemoryVectorMemory:
    """Deterministic vector memory used by tests and single-node deployments."""

    def __init__(self) -> None:
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._payloads: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def upsert(self, incident_id: str, vector: tuple[float, ...], payload: dict[str, Any]) -> None:
        with self._lock:
            self._vectors[incident_id] = vector
            self._payloads[incident_id] = dict(payload)

    def search(self, vector: tuple[float, ...], *, limit: int = 5) -> tuple[tuple[str, float, dict[str, Any]], ...]:
        with self._lock:
            scored = [
                (incident_id, cosine_similarity(vector, stored), dict(self._payloads.get(incident_id, {})))
                for incident_id, stored in self._vectors.items()
            ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return tuple(scored[:limit])


class QdrantVectorMemory:
    """Qdrant-backed vector memory adapter for production SOC deployment."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        collection_name: str = "anubis_threat_intel",
        dimensions: int = 128,
        client: Any | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.dimensions = dimensions
        if client is not None:
            self.client = client
        else:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams
            except ImportError as exc:  # pragma: no cover - deployment dependency guard
                raise RuntimeError("qdrant-client is required for QdrantVectorMemory") from exc
            self.client = QdrantClient(url=url)
            self.client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )

    def upsert(self, incident_id: str, vector: tuple[float, ...], payload: dict[str, Any]) -> None:
        try:
            from qdrant_client.models import PointStruct
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("qdrant-client is required for QdrantVectorMemory") from exc
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=incident_id, vector=list(vector), payload=dict(payload))],
        )

    def search(self, vector: tuple[float, ...], *, limit: int = 5) -> tuple[tuple[str, float, dict[str, Any]], ...]:
        results = self.client.search(collection_name=self.collection_name, query_vector=list(vector), limit=limit)
        return tuple((str(result.id), float(result.score), dict(result.payload or {})) for result in results)


class IncidentMemorySystem:
    """Stores incidents and embeds behavior patterns for similarity search."""

    def __init__(
        self,
        *,
        store: IncidentStore | None = None,
        vector_memory: VectorMemory | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self.store = store or IncidentStore()
        self.vector_memory = vector_memory or InMemoryVectorMemory()
        self.embedder = embedder or HashEmbeddingProvider()

    def store_incident(
        self,
        classification: RiskClassification,
        *,
        response: SOCResponseResult | None = None,
        verdict: IncidentVerdict = IncidentVerdict.UNKNOWN,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        pattern = self.pattern_text(classification, response=response)
        incident = IncidentRecord(
            incident_id=f"incident_{uuid4().hex}",
            classification=classification,
            response=response,
            verdict=verdict,
            notes=notes,
            pattern_text=pattern,
            metadata=dict(metadata or {}),
        )
        self.store.save(incident)
        self.vector_memory.upsert(incident.incident_id, self.embedder.embed(pattern), incident.to_dict())
        return incident

    def mark_false_positive(self, incident_id: str, *, notes: str = "") -> IncidentRecord:
        return self.store.update_verdict(incident_id, IncidentVerdict.FALSE_POSITIVE, notes=notes)

    def mark_true_positive(self, incident_id: str, *, notes: str = "") -> IncidentRecord:
        return self.store.update_verdict(incident_id, IncidentVerdict.TRUE_POSITIVE, notes=notes)

    def similar_incidents(self, classification: RiskClassification, *, limit: int = 5, min_score: float = 0.0) -> tuple[SimilarIncident, ...]:
        vector = self.embedder.embed(self.pattern_text(classification))
        matches: list[SimilarIncident] = []
        for incident_id, score, _payload in self.vector_memory.search(vector, limit=limit):
            if score < min_score:
                continue
            incident = self.store.get(incident_id)
            if incident is not None:
                matches.append(SimilarIncident(incident=incident, score=score))
        return tuple(matches)

    def incidents(self) -> tuple[IncidentRecord, ...]:
        return self.store.all()

    def pattern_text(self, classification: RiskClassification, *, response: SOCResponseResult | None = None) -> str:
        event = classification.event
        finding_text = " ".join(f"{finding.category.value}:{finding.code.value}:{finding.reason}" for finding in classification.findings)
        response_text = ""
        if response is not None:
            response_text = " ".join(action.action_type.value for action in response.actions)
        return " ".join(
            item
            for item in (
                f"agent={event.agent_id}",
                f"task={event.task_id}",
                f"event={event.event_type}",
                f"score={int(classification.score)}",
                f"payload={event.payload}",
                finding_text,
                response_text,
            )
            if item
        )


class LearningFeedbackLoop:
    """Refines anomaly thresholds from confirmed incidents and false positives."""

    def __init__(self, memory: IncidentMemorySystem) -> None:
        self.memory = memory

    def refine_baseline(self, baseline: BehaviorBaseline | None = None) -> LearningFeedbackResult:
        current = baseline or BehaviorBaseline.default()
        incidents = self.memory.incidents()
        false_positives = tuple(incident for incident in incidents if incident.verdict == IncidentVerdict.FALSE_POSITIVE)
        true_positives = tuple(incident for incident in incidents if incident.verdict == IncidentVerdict.TRUE_POSITIVE)
        adjustments: list[LearningAdjustment] = []

        repeated_failure_fp = _count_code(false_positives, AnomalyCode.REPEATED_FAILURES)
        repeated_failure_tp = _count_code(true_positives, AnomalyCode.REPEATED_FAILURES)
        repeated_action_fp = _count_code(false_positives, AnomalyCode.INFINITE_LOOP)
        repeated_action_tp = _count_code(true_positives, AnomalyCode.INFINITE_LOOP)
        mass_write_fp = _count_code(false_positives, AnomalyCode.MASS_FILE_MODIFICATION)
        mass_write_tp = _count_code(true_positives, AnomalyCode.MASS_FILE_MODIFICATION)

        new_repeated_failure = _adjust_threshold(
            current.repeated_failure_threshold,
            false_positive_count=repeated_failure_fp,
            true_positive_count=repeated_failure_tp,
        )
        new_repeated_action = _adjust_threshold(
            current.repeated_action_threshold,
            false_positive_count=repeated_action_fp,
            true_positive_count=repeated_action_tp,
        )
        new_mass_write = _adjust_threshold(
            current.mass_file_write_threshold,
            false_positive_count=mass_write_fp,
            true_positive_count=mass_write_tp,
        )

        if new_repeated_failure != current.repeated_failure_threshold:
            adjustments.append(_adjustment("repeated_failure_threshold", current.repeated_failure_threshold, new_repeated_failure, repeated_failure_fp, repeated_failure_tp))
        if new_repeated_action != current.repeated_action_threshold:
            adjustments.append(_adjustment("repeated_action_threshold", current.repeated_action_threshold, new_repeated_action, repeated_action_fp, repeated_action_tp))
        if new_mass_write != current.mass_file_write_threshold:
            adjustments.append(_adjustment("mass_file_write_threshold", current.mass_file_write_threshold, new_mass_write, mass_write_fp, mass_write_tp))

        refined = replace(
            current,
            repeated_failure_threshold=new_repeated_failure,
            repeated_action_threshold=new_repeated_action,
            mass_file_write_threshold=new_mass_write,
        )
        return LearningFeedbackResult(
            baseline=refined,
            adjustments=tuple(adjustments),
            false_positive_count=len(false_positives),
            true_positive_count=len(true_positives),
        )


class ThreatIntelDB:
    """Facade combining incident storage, vector memory, and feedback learning."""

    def __init__(self, memory: IncidentMemorySystem | None = None) -> None:
        self.memory = memory or IncidentMemorySystem()
        self.feedback = LearningFeedbackLoop(self.memory)

    def record_incident(
        self,
        classification: RiskClassification,
        *,
        response: SOCResponseResult | None = None,
        verdict: IncidentVerdict = IncidentVerdict.UNKNOWN,
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        return self.memory.store_incident(
            classification,
            response=response,
            verdict=verdict,
            notes=notes,
            metadata=metadata,
        )

    def similar_attacks(self, classification: RiskClassification, *, limit: int = 5, min_score: float = 0.0) -> tuple[SimilarIncident, ...]:
        return self.memory.similar_incidents(classification, limit=limit, min_score=min_score)

    def mark_false_positive(self, incident_id: str, *, notes: str = "") -> IncidentRecord:
        return self.memory.mark_false_positive(incident_id, notes=notes)

    def mark_true_positive(self, incident_id: str, *, notes: str = "") -> IncidentRecord:
        return self.memory.mark_true_positive(incident_id, notes=notes)

    def refine_detection_baseline(self, baseline: BehaviorBaseline | None = None) -> LearningFeedbackResult:
        return self.feedback.refine_baseline(baseline)


def _count_code(incidents: tuple[IncidentRecord, ...], code: AnomalyCode) -> int:
    return sum(1 for incident in incidents for finding in incident.classification.findings if finding.code == code)


def _adjust_threshold(value: int, *, false_positive_count: int, true_positive_count: int) -> int:
    if false_positive_count > true_positive_count:
        return value + 1
    if true_positive_count > false_positive_count and value > 1:
        return value - 1
    return value


def _adjustment(field: str, old: int, new: int, false_positives: int, true_positives: int) -> LearningAdjustment:
    direction = "raised" if new > old else "lowered"
    reason = f"{direction} from false_positive={false_positives}, true_positive={true_positives}"
    return LearningAdjustment(field=field, old_value=old, new_value=new, reason=reason)


__all__ = [
    "IncidentMemorySystem",
    "IncidentRecord",
    "IncidentStore",
    "IncidentVerdict",
    "InMemoryVectorMemory",
    "LearningAdjustment",
    "LearningFeedbackLoop",
    "LearningFeedbackResult",
    "QdrantVectorMemory",
    "SimilarIncident",
    "ThreatIntelDB",
    "VectorMemory",
]
