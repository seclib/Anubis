"""Memory scoring and routing for Anubis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp
from re import findall
from typing import Any, Literal


MemorySource = Literal["obsidian", "qdrant", "hybrid"]
MemoryKind = Literal["obsidian", "qdrant"]


@dataclass(frozen=True)
class MemoryCandidate:
    source: MemoryKind
    content: str
    qdrant_similarity: float = 0.0
    title: str = ""
    tags: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    updated_at: datetime | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredMemory:
    candidate: MemoryCandidate
    qdrant_score: float
    obsidian_score: float
    recency_bonus: float
    confidence_bonus: float
    final_score: float


@dataclass(frozen=True)
class Conflict:
    obsidian: ScoredMemory
    qdrant: ScoredMemory
    reason: str


@dataclass(frozen=True)
class MemoryRoutingDecision:
    selected_memory_source: MemorySource
    retrieved_context: list[MemoryCandidate]
    confidence_score: float
    conflict_flag: bool
    conflicts: list[Conflict] = field(default_factory=list)


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "to",
    "use",
    "what",
    "with",
}

NEGATION_TERMS = {"not", "never", "no", "must not", "do not", "forbidden"}
QDRANT_MIN_SCORE = 0.35
OBSIDIAN_MIN_SCORE = 0.35
HYBRID_MIN_SCORE = 0.30
CONFLICT_ENTITY_OVERLAP = 0.35
CONTEXT_LIMIT = 8
TRUTH_INTENT_TERMS = {
    "canonical",
    "decision",
    "fact",
    "ground",
    "grounded",
    "policy",
    "rule",
    "skill",
    "source",
    "truth",
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in findall(r"[a-zA-Z0-9_]+", text.lower())
        if token and token not in STOPWORDS
    }


def qdrant_similarity_score(candidate: MemoryCandidate) -> float:
    if candidate.source != "qdrant":
        return 0.0
    return clamp(candidate.qdrant_similarity)


def obsidian_keyword_skill_score(query: str, candidate: MemoryCandidate) -> float:
    if candidate.source != "obsidian":
        return 0.0

    query_terms = tokenize(query)
    title_terms = tokenize(candidate.title)
    tag_terms = {tag.lower() for tag in candidate.tags}
    skill_terms = {skill.lower() for skill in candidate.skills}
    keyword_terms = {keyword.lower() for keyword in candidate.keywords} | tokenize(candidate.content)

    title_score = overlap_score(query_terms, title_terms)
    tag_score = overlap_score(query_terms, tag_terms)
    skill_score = overlap_score(query_terms, skill_terms)
    keyword_score = overlap_score(query_terms, keyword_terms)

    return clamp(
        (0.25 * title_score)
        + (0.15 * tag_score)
        + (0.25 * skill_score)
        + (0.35 * keyword_score)
    )


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def recency_score(
    updated_at: datetime | None,
    *,
    now: datetime | None = None,
    half_life_days: float = 90.0,
) -> float:
    if updated_at is None:
        return 0.0

    current = now or datetime.now(timezone.utc)
    updated = updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)

    age_seconds = max(0.0, (current - updated).total_seconds())
    age_days = age_seconds / 86_400.0
    return clamp(exp(-age_days / half_life_days))


def confidence_score(candidate: MemoryCandidate) -> float:
    metadata_confidence = float(candidate.metadata.get("confidence", 0.0) or 0.0)
    authority = str(candidate.metadata.get("authority", "")).lower()
    status = str(candidate.metadata.get("status", "")).lower()

    authority_bonus = {
        "canonical": 1.0,
        "high": 0.9,
        "approved": 0.85,
        "active": 0.75,
        "medium": 0.6,
        "draft": 0.35,
        "low": 0.25,
        "deprecated": 0.05,
    }.get(authority, 0.0)

    status_bonus = {
        "canonical": 1.0,
        "approved": 0.85,
        "active": 0.75,
        "draft": 0.35,
        "deprecated": 0.05,
    }.get(status, 0.0)

    declared = max(candidate.confidence, metadata_confidence)
    return clamp(max(declared, authority_bonus, status_bonus))


def score_memory_candidate(
    query: str,
    candidate: MemoryCandidate,
    *,
    now: datetime | None = None,
) -> ScoredMemory:
    q_score = qdrant_similarity_score(candidate)
    o_score = obsidian_keyword_skill_score(query, candidate)
    recency_bonus = 0.10 * recency_score(candidate.updated_at, now=now)
    confidence_bonus = 0.10 * confidence_score(candidate)

    final_score = clamp(
        (q_score * 0.40)
        + (o_score * 0.60)
        + recency_bonus
        + confidence_bonus
    )

    return ScoredMemory(
        candidate=candidate,
        qdrant_score=q_score,
        obsidian_score=o_score,
        recency_bonus=recency_bonus,
        confidence_bonus=confidence_bonus,
        final_score=final_score,
    )


def score_memories(
    query: str,
    candidates: list[MemoryCandidate],
    *,
    now: datetime | None = None,
) -> list[ScoredMemory]:
    scored = [score_memory_candidate(query, candidate, now=now) for candidate in candidates]
    return sorted(scored, key=lambda item: item.final_score, reverse=True)


def detect_conflicts(scored_memories: list[ScoredMemory]) -> list[Conflict]:
    obsidian_memories = [item for item in scored_memories if item.candidate.source == "obsidian"]
    qdrant_memories = [item for item in scored_memories if item.candidate.source == "qdrant"]
    conflicts: list[Conflict] = []

    for obsidian in obsidian_memories:
        for qdrant in qdrant_memories:
            if memories_disagree(obsidian.candidate.content, qdrant.candidate.content):
                conflicts.append(
                    Conflict(
                        obsidian=obsidian,
                        qdrant=qdrant,
                        reason="Obsidian and Qdrant contain overlapping entities with incompatible polarity.",
                    )
                )

    return conflicts


def memories_disagree(obsidian_text: str, qdrant_text: str) -> bool:
    obsidian_terms = tokenize(obsidian_text)
    qdrant_terms = tokenize(qdrant_text)
    if overlap_score(obsidian_terms, qdrant_terms) < CONFLICT_ENTITY_OVERLAP:
        return False

    obsidian_negative = has_negation(obsidian_text)
    qdrant_negative = has_negation(qdrant_text)
    return obsidian_negative != qdrant_negative


def has_negation(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in NEGATION_TERMS)


def route_memory(
    query: str,
    qdrant_candidates: list[MemoryCandidate],
    obsidian_candidates: list[MemoryCandidate],
    *,
    now: datetime | None = None,
    context_limit: int = CONTEXT_LIMIT,
) -> MemoryRoutingDecision:
    all_candidates = [
        *[candidate for candidate in qdrant_candidates if candidate.source == "qdrant"],
        *[candidate for candidate in obsidian_candidates if candidate.source == "obsidian"],
    ]
    scored = score_memories(query, all_candidates, now=now)
    conflicts = detect_conflicts(scored)
    conflict_flag = bool(conflicts)

    scored = apply_conflict_priority(scored, conflicts)
    best_qdrant = best_source_score(scored, "qdrant")
    best_obsidian = best_source_score(scored, "obsidian")
    truth_required = query_requires_truth(query)

    if conflict_flag and best_obsidian >= OBSIDIAN_MIN_SCORE:
        selected = "obsidian"
    elif truth_required and best_obsidian >= HYBRID_MIN_SCORE:
        selected = "hybrid" if best_qdrant >= QDRANT_MIN_SCORE else "obsidian"
    elif best_obsidian >= OBSIDIAN_MIN_SCORE and best_qdrant >= QDRANT_MIN_SCORE:
        selected = "hybrid"
    elif best_obsidian >= OBSIDIAN_MIN_SCORE:
        selected = "obsidian"
    elif best_qdrant >= QDRANT_MIN_SCORE:
        selected = "qdrant"
    elif best_obsidian >= HYBRID_MIN_SCORE and best_qdrant >= HYBRID_MIN_SCORE:
        selected = "hybrid"
    else:
        selected = "obsidian" if best_obsidian >= best_qdrant else "qdrant"

    selected_scored = select_context(scored, selected, context_limit=context_limit)
    confidence = aggregate_confidence(selected_scored, conflict_flag=conflict_flag)

    return MemoryRoutingDecision(
        selected_memory_source=selected,
        retrieved_context=[item.candidate for item in selected_scored],
        confidence_score=confidence,
        conflict_flag=conflict_flag,
        conflicts=conflicts,
    )


def apply_conflict_priority(
    scored_memories: list[ScoredMemory],
    conflicts: list[Conflict],
) -> list[ScoredMemory]:
    conflicted_qdrant_ids = {id(conflict.qdrant.candidate) for conflict in conflicts}
    adjusted: list[ScoredMemory] = []

    for item in scored_memories:
        if item.candidate.source == "qdrant" and id(item.candidate) in conflicted_qdrant_ids:
            adjusted.append(
                ScoredMemory(
                    candidate=item.candidate,
                    qdrant_score=item.qdrant_score,
                    obsidian_score=item.obsidian_score,
                    recency_bonus=item.recency_bonus,
                    confidence_bonus=item.confidence_bonus,
                    final_score=clamp(item.final_score * 0.25),
                )
            )
        else:
            adjusted.append(item)

    return sorted(adjusted, key=lambda memory: memory.final_score, reverse=True)


def query_requires_truth(query: str) -> bool:
    return bool(tokenize(query) & TRUTH_INTENT_TERMS)


def best_source_score(scored_memories: list[ScoredMemory], source: MemoryKind) -> float:
    return max(
        (item.final_score for item in scored_memories if item.candidate.source == source),
        default=0.0,
    )


def select_context(
    scored_memories: list[ScoredMemory],
    selected_source: MemorySource,
    *,
    context_limit: int,
) -> list[ScoredMemory]:
    if selected_source == "hybrid":
        selected = scored_memories
    else:
        selected = [item for item in scored_memories if item.candidate.source == selected_source]
    return selected[: max(1, context_limit)]


def aggregate_confidence(
    selected_scored: list[ScoredMemory],
    *,
    conflict_flag: bool,
) -> float:
    if not selected_scored:
        return 0.0

    top_score = selected_scored[0].final_score
    average_score = sum(item.final_score for item in selected_scored) / len(selected_scored)
    source_confidence = max(confidence_score(item.candidate) for item in selected_scored)
    confidence = (0.50 * top_score) + (0.25 * average_score) + (0.25 * source_confidence)

    if conflict_flag:
        confidence *= 0.85

    return round(clamp(confidence), 6)


def example_usage() -> MemoryRoutingDecision:
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    query = "Should Anubis use Obsidian or Qdrant as the truth layer?"

    qdrant_candidates = [
        MemoryCandidate(
            source="qdrant",
            content="Anubis should use Qdrant as the truth layer for memory.",
            qdrant_similarity=0.92,
            updated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            confidence=0.72,
        )
    ]

    obsidian_candidates = [
        MemoryCandidate(
            source="obsidian",
            title="Anubis Truth Layer",
            content="Anubis must not use Qdrant as the truth layer. Obsidian is ground truth memory.",
            tags=("anubis", "memory", "truth"),
            skills=("memory-routing",),
            keywords=("obsidian", "qdrant", "truth", "layer"),
            updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            confidence=0.95,
            metadata={"status": "canonical", "authority": "canonical"},
        )
    ]

    return route_memory(
        query=query,
        qdrant_candidates=qdrant_candidates,
        obsidian_candidates=obsidian_candidates,
        now=now,
    )


if __name__ == "__main__":
    decision = example_usage()
    print(
        {
            "selected_memory_source": decision.selected_memory_source,
            "retrieved_context": [item.content for item in decision.retrieved_context],
            "confidence_score": decision.confidence_score,
            "conflict_flag": decision.conflict_flag,
        }
    )


__all__ = [
    "Conflict",
    "MemoryCandidate",
    "MemoryRoutingDecision",
    "ScoredMemory",
    "aggregate_confidence",
    "apply_conflict_priority",
    "confidence_score",
    "detect_conflicts",
    "example_usage",
    "obsidian_keyword_skill_score",
    "qdrant_similarity_score",
    "query_requires_truth",
    "recency_score",
    "route_memory",
    "score_memories",
]
