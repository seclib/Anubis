"""Memory routing for Obsidian truth and Qdrant semantic recall."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Literal, Mapping, Protocol

from retrieval.memory_scoring import (
    MemoryCandidate,
    MemoryRoutingDecision,
    ScoredMemory,
    detect_conflicts,
    score_memories,
    tokenize,
)


RouteIntent = Literal["truth", "semantic", "procedural", "hybrid"]
Backend = Literal["obsidian", "qdrant", "hybrid"]

TRUTH_TERMS = {
    "canonical",
    "current",
    "decision",
    "definition",
    "fact",
    "policy",
    "rule",
    "source",
    "truth",
}
PROCEDURE_TERMS = {
    "checklist",
    "how",
    "playbook",
    "procedure",
    "runbook",
    "skill",
    "steps",
    "workflow",
}
SEMANTIC_TERMS = {
    "analogous",
    "example",
    "like",
    "pattern",
    "recall",
    "related",
    "similar",
}


class Retriever(Protocol):
    def search(self, query: str, limit: int = 8) -> list[Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class QueryClassification:
    intent: RouteIntent
    obsidian_weight: float
    qdrant_weight: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FusedContextItem:
    source: Backend
    content: str
    score: float
    title: str = ""
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRouteResult:
    query: str
    classification: QueryClassification
    decision: MemoryRoutingDecision
    context: tuple[FusedContextItem, ...]
    scores: tuple[ScoredMemory, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "classification": asdict(self.classification),
            "decision": {
                "selected_memory_source": self.decision.selected_memory_source,
                "confidence_score": self.decision.confidence_score,
                "conflict_flag": self.decision.conflict_flag,
                "conflicts": [conflict.reason for conflict in self.decision.conflicts],
            },
            "context": [asdict(item) for item in self.context],
            "scores": [
                {
                    "source": scored.candidate.source,
                    "title": scored.candidate.title,
                    "final_score": scored.final_score,
                    "qdrant_score": scored.qdrant_score,
                    "obsidian_score": scored.obsidian_score,
                }
                for scored in self.scores
            ],
        }


class QueryClassifier:
    def classify(self, query: str) -> QueryClassification:
        terms = tokenize(query)
        truth = len(terms & TRUTH_TERMS)
        procedural = len(terms & PROCEDURE_TERMS)
        semantic = len(terms & SEMANTIC_TERMS)
        reasons: list[str] = []
        if truth:
            reasons.append("truth_terms")
        if procedural:
            reasons.append("procedure_terms")
        if semantic:
            reasons.append("semantic_terms")

        if truth or procedural:
            obsidian = min(1.0, 0.65 + 0.12 * truth + 0.10 * procedural)
            qdrant = min(1.0, 0.30 + 0.12 * semantic)
            intent: RouteIntent = "procedural" if procedural >= truth else "truth"
            if semantic:
                intent = "hybrid"
                qdrant = max(qdrant, 0.55)
            return QueryClassification(intent, obsidian, qdrant, tuple(reasons))

        if semantic:
            return QueryClassification("semantic", 0.35, min(1.0, 0.70 + 0.10 * semantic), tuple(reasons))

        return QueryClassification("hybrid", 0.55, 0.55, ("default_hybrid",))


class ContextMerger:
    def merge(
        self,
        scored: Iterable[ScoredMemory],
        *,
        selected: Backend,
        limit: int = 8,
    ) -> tuple[FusedContextItem, ...]:
        deduped: dict[str, FusedContextItem] = {}
        for item in scored:
            candidate = item.candidate
            if selected != "hybrid" and candidate.source != selected:
                continue
            key = self._key(candidate)
            score = self._fusion_score(item)
            existing = deduped.get(key)
            fused = FusedContextItem(
                source=candidate.source,
                content=candidate.content,
                score=score,
                title=candidate.title,
                path=str(candidate.metadata.get("path") or candidate.metadata.get("source") or ""),
                metadata=dict(candidate.metadata),
            )
            if existing is None or fused.score > existing.score:
                deduped[key] = fused
        results = sorted(deduped.values(), key=lambda item: (item.score, item.source == "obsidian"), reverse=True)
        return tuple(results[: max(1, limit)])

    def _fusion_score(self, scored: ScoredMemory) -> float:
        truth_bonus = 0.08 if scored.candidate.source == "obsidian" else 0.0
        semantic_bonus = 0.04 if scored.candidate.source == "qdrant" else 0.0
        return round(min(1.0, scored.final_score + truth_bonus + semantic_bonus), 6)

    def _key(self, candidate: MemoryCandidate) -> str:
        path = str(candidate.metadata.get("path") or candidate.title)
        text = " ".join(candidate.content.split())[:240]
        return f"{candidate.source}:{path}:{text}"


class MemoryRouter:
    def __init__(
        self,
        *,
        obsidian: Retriever | Callable[[str, int], list[Mapping[str, Any]]] | None = None,
        qdrant: Retriever | Callable[[str, int], list[Mapping[str, Any]]] | None = None,
        classifier: QueryClassifier | None = None,
        merger: ContextMerger | None = None,
    ) -> None:
        self.obsidian = obsidian
        self.qdrant = qdrant
        self.classifier = classifier or QueryClassifier()
        self.merger = merger or ContextMerger()

    def route(self, query: str, *, limit: int = 8) -> MemoryRouteResult:
        classification = self.classifier.classify(query)
        obsidian_rows = self._retrieve(self.obsidian, query, limit) if classification.obsidian_weight > 0 else []
        qdrant_rows = self._retrieve(self.qdrant, query, limit) if classification.qdrant_weight > 0 else []
        obsidian_candidates = [to_candidate(row, "obsidian") for row in obsidian_rows]
        qdrant_candidates = [to_candidate(row, "qdrant") for row in qdrant_rows]
        decision = route_with_classification(
            query,
            classification,
            obsidian_candidates=obsidian_candidates,
            qdrant_candidates=qdrant_candidates,
            context_limit=limit,
        )
        scored = tuple(score_memories(query, [*obsidian_candidates, *qdrant_candidates]))
        merged = self.merger.merge(scored, selected=decision.selected_memory_source, limit=limit)
        return MemoryRouteResult(query, classification, decision, merged, scored)

    def _retrieve(
        self,
        retriever: Retriever | Callable[[str, int], list[Mapping[str, Any]]] | None,
        query: str,
        limit: int,
    ) -> list[Mapping[str, Any]]:
        if retriever is None:
            return []
        if callable(retriever) and not hasattr(retriever, "search"):
            return list(retriever(query, limit))
        return list(retriever.search(query, limit))  # type: ignore[union-attr]


def route_with_classification(
    query: str,
    classification: QueryClassification,
    *,
    obsidian_candidates: list[MemoryCandidate],
    qdrant_candidates: list[MemoryCandidate],
    context_limit: int = 8,
) -> MemoryRoutingDecision:
    scored = score_memories(query, [*obsidian_candidates, *qdrant_candidates])
    conflicts = detect_conflicts(scored)
    best_obsidian = max((item.final_score for item in scored if item.candidate.source == "obsidian"), default=0.0)
    best_qdrant = max((item.final_score for item in scored if item.candidate.source == "qdrant"), default=0.0)

    weighted_obsidian = best_obsidian * classification.obsidian_weight
    weighted_qdrant = best_qdrant * classification.qdrant_weight

    if conflicts and best_obsidian > 0:
        selected: Backend = "obsidian"
    elif classification.intent in {"truth", "procedural"} and best_obsidian > 0:
        selected = "obsidian" if weighted_obsidian >= weighted_qdrant * 0.85 else "hybrid"
    elif classification.intent == "semantic" and best_qdrant > 0:
        selected = "qdrant" if weighted_qdrant >= weighted_obsidian else "hybrid"
    elif best_obsidian and best_qdrant:
        selected = "hybrid"
    elif best_obsidian:
        selected = "obsidian"
    elif best_qdrant:
        selected = "qdrant"
    else:
        selected = "hybrid"

    selected_scored = [
        item for item in scored if selected == "hybrid" or item.candidate.source == selected
    ][: max(1, context_limit)]
    confidence = aggregate_route_confidence(selected_scored, selected, bool(conflicts), classification)
    return MemoryRoutingDecision(
        selected_memory_source=selected,
        retrieved_context=[item.candidate for item in selected_scored],
        confidence_score=confidence,
        conflict_flag=bool(conflicts),
        conflicts=conflicts,
    )


def aggregate_route_confidence(
    selected: list[ScoredMemory],
    backend: Backend,
    conflict: bool,
    classification: QueryClassification,
) -> float:
    if not selected:
        return 0.0
    top = selected[0].final_score
    average = sum(item.final_score for item in selected) / len(selected)
    route_weight = classification.obsidian_weight if backend == "obsidian" else classification.qdrant_weight if backend == "qdrant" else 0.60
    value = 0.45 * top + 0.30 * average + 0.25 * route_weight
    if conflict:
        value *= 0.85
    return round(max(0.0, min(1.0, value)), 6)


def to_candidate(row: Mapping[str, Any], source: Literal["obsidian", "qdrant"]) -> MemoryCandidate:
    metadata = dict(row.get("metadata") or row.get("payload") or {})
    if row.get("path") and "path" not in metadata:
        metadata["path"] = row.get("path")
    return MemoryCandidate(
        source=source,
        content=str(row.get("text") or row.get("content") or row.get("markdown") or ""),
        qdrant_similarity=float(row.get("score") or row.get("similarity") or 0.0) if source == "qdrant" else 0.0,
        title=str(row.get("title") or row.get("heading") or row.get("path") or ""),
        tags=tuple(str(tag) for tag in row.get("tags", ()) if str(tag)),
        skills=tuple(str(skill) for skill in row.get("skills", ()) if str(skill)),
        keywords=tuple(str(keyword) for keyword in row.get("keywords", ()) if str(keyword)),
        confidence=float(row.get("confidence") or metadata.get("confidence") or 0.0),
        metadata=metadata,
    )


__all__ = [
    "Backend",
    "ContextMerger",
    "FusedContextItem",
    "MemoryRouteResult",
    "MemoryRouter",
    "QueryClassification",
    "QueryClassifier",
    "RouteIntent",
    "aggregate_route_confidence",
    "route_with_classification",
    "to_candidate",
]
