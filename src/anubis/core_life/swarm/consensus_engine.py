from __future__ import annotations

from dataclasses import dataclass, field

from anubis.core_life.swarm.agent_registry import AgentInsight, ResearchRole


@dataclass(frozen=True, slots=True)
class SwarmVote:
    agent_name: str
    role: ResearchRole
    decision: str
    confidence: float
    weight: float
    rationale: str


@dataclass(frozen=True, slots=True)
class ConsensusOutcome:
    decision: str
    confidence: float
    votes: tuple[SwarmVote, ...]
    conflicts: tuple[str, ...] = field(default_factory=tuple)
    explanation: tuple[str, ...] = field(default_factory=tuple)


class ConsensusEngine:
    role_weights = {
        ResearchRole.PLANNER: 0.9,
        ResearchRole.EXECUTOR: 1.0,
        ResearchRole.ANALYST: 1.1,
        ResearchRole.CRITIC: 1.15,
        ResearchRole.SYNTHESIZER: 1.2,
    }

    def decide(self, insights: tuple[AgentInsight, ...], scores: dict[str, float]) -> ConsensusOutcome:
        votes = tuple(self._vote(insight, scores.get(insight.agent_name, 0.5)) for insight in insights)
        totals: dict[str, float] = {}
        for vote in votes:
            totals[vote.decision] = totals.get(vote.decision, 0.0) + vote.weight
        if not totals:
            return ConsensusOutcome(
                decision="no_decision",
                confidence=0.0,
                votes=(),
                explanation=("No agent outputs were available for consensus.",),
            )
        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        decision, score = ranked[0]
        total = sum(totals.values())
        conflicts = tuple(item[0] for item in ranked[1:] if item[1] > 0)
        return ConsensusOutcome(
            decision=decision,
            confidence=score / total if total else 0.0,
            votes=votes,
            conflicts=conflicts,
            explanation=(
                f"Decision '{decision}' selected by weighted swarm consensus.",
                f"Vote totals: {dict(sorted(totals.items()))}.",
            ),
        )

    def _vote(self, insight: AgentInsight, score: float) -> SwarmVote:
        return SwarmVote(
            agent_name=insight.agent_name,
            role=insight.role,
            decision=insight.recommendation,
            confidence=insight.confidence,
            weight=insight.confidence * score * self.role_weights[insight.role],
            rationale=insight.summary,
        )
