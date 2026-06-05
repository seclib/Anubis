"""Deterministic consensus for ANUBIS swarm outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SwarmVote:
    agent: str
    decision: str
    confidence: float
    weight: float
    rationale: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")

    @property
    def score(self) -> float:
        return round(self.confidence * self.weight, 6)

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "decision": self.decision,
            "confidence": self.confidence,
            "weight": self.weight,
            "score": self.score,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class SwarmDecision:
    accepted: bool
    decision: str
    score: float
    votes: tuple[SwarmVote, ...]
    explanation: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "decision": self.decision,
            "score": self.score,
            "votes": tuple(vote.to_dict() for vote in self.votes),
            "explanation": self.explanation,
        }


class SwarmConsensus:
    def __init__(self, *, threshold: float = 0.5) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold

    def decide(self, votes: tuple[SwarmVote, ...]) -> SwarmDecision:
        if not votes:
            return SwarmDecision(False, "no_decision", 0.0, (), ("No votes supplied.",))
        totals: dict[str, float] = {}
        for vote in votes:
            totals[vote.decision] = totals.get(vote.decision, 0.0) + vote.score
        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        decision, score = ranked[0]
        total_score = sum(totals.values()) or 1.0
        normalized = round(score / total_score, 6)
        return SwarmDecision(
            accepted=normalized >= self.threshold,
            decision=decision,
            score=normalized,
            votes=tuple(sorted(votes, key=lambda vote: vote.agent)),
            explanation=(
                f"Selected '{decision}' with normalized score {normalized}.",
                "Ties are resolved lexicographically for determinism.",
            ),
        )

    @staticmethod
    def vote_from_agent_result(
        *,
        agent_name: str,
        result: Mapping[str, object],
        weight: float,
    ) -> SwarmVote:
        ok = bool(result.get("ok"))
        return SwarmVote(
            agent=agent_name,
            decision="accept" if ok else "revise",
            confidence=0.8 if ok else 0.6,
            weight=weight,
            rationale="Vote derived from structured agent result.",
        )


__all__ = ["SwarmConsensus", "SwarmDecision", "SwarmVote"]
