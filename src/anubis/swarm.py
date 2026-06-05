from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.agents import AgentRegistry
from anubis.types import AgentDescriptor


class SwarmRole(StrEnum):
    COORDINATOR = "coordinator"
    INVESTIGATOR = "investigator"
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    OBSERVER = "observer"


class ConsensusStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TIED = "tied"
    INSUFFICIENT_QUORUM = "insufficient_quorum"


class PerformanceOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class RoleProfile:
    role: SwarmRole
    required_capabilities: frozenset[str]
    priority: int
    max_agents: int = 1
    reason: str = ""

    def __post_init__(self) -> None:
        if self.priority < 1:
            raise ValueError("priority must be at least 1")
        if self.max_agents < 1:
            raise ValueError("max_agents must be at least 1")
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    role: SwarmRole
    agent_name: str
    capabilities: frozenset[str]
    priority: int
    reason: str
    performance_score: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.performance_score <= 1:
            raise ValueError("performance_score must be between 0 and 1")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True, slots=True)
class SwarmSession:
    objective: str
    assignments: tuple[RoleAssignment, ...]
    id: str = field(default_factory=lambda: f"swarm_{uuid4().hex}")
    metadata: Mapping[str, Any] = field(default_factory=dict)
    explanation: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def agents_for_role(self, role: SwarmRole) -> tuple[str, ...]:
        return tuple(
            assignment.agent_name for assignment in self.assignments if assignment.role == role
        )


@dataclass(frozen=True, slots=True)
class Proposal:
    agent_name: str
    role: SwarmRole
    decision: str
    confidence: float
    rationale: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class Vote:
    agent_name: str
    role: SwarmRole
    decision: str
    weight: float
    rationale: str

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError("weight must be non-negative")


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    status: ConsensusStatus
    decision: str | None
    score: float
    quorum: int
    votes: tuple[Vote, ...]
    conflicts: tuple[str, ...]
    explanation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentScore:
    agent_name: str
    score: float = 0.5
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    rollbacks: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 1:
            raise ValueError("score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PerformanceUpdate:
    agent_name: str
    outcome: PerformanceOutcome
    delta: float
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class RoleSwitchResult:
    session: SwarmSession
    changed: bool
    replacements: Mapping[str, str]
    explanation: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "replacements", MappingProxyType(dict(self.replacements)))


class SwarmCoordinator:
    """Deterministic multi-agent coordination and consensus engine."""

    def __init__(
        self,
        *,
        role_profiles: Sequence[RoleProfile] | None = None,
        agent_registry: AgentRegistry | None = None,
        quorum: int = 1,
        acceptance_threshold: float = 0.5,
        minimum_replacement_score: float = 0.25,
    ) -> None:
        if quorum < 1:
            raise ValueError("quorum must be at least 1")
        if not 0 < acceptance_threshold <= 1:
            raise ValueError("acceptance_threshold must be in (0, 1]")
        if not 0 <= minimum_replacement_score <= 1:
            raise ValueError("minimum_replacement_score must be between 0 and 1")
        self._profiles = tuple(role_profiles or default_role_profiles())
        self._agent_registry = agent_registry
        self._quorum = quorum
        self._acceptance_threshold = acceptance_threshold
        self._minimum_replacement_score = minimum_replacement_score
        self._scores: dict[str, AgentScore] = {}

    async def create_session(
        self,
        objective: str,
        *,
        agents: Sequence[AgentDescriptor] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SwarmSession:
        available_agents = await self._resolve_agents(agents)
        assignments, explanations = self.assign_roles(available_agents)
        return SwarmSession(
            objective=objective,
            assignments=assignments,
            metadata=metadata or {},
            explanation=(
                f"Created swarm session for objective: {objective}.",
                *explanations,
            ),
        )

    def assign_roles(
        self,
        agents: Sequence[AgentDescriptor],
    ) -> tuple[tuple[RoleAssignment, ...], tuple[str, ...]]:
        sorted_agents = tuple(sorted(agents, key=lambda agent: agent.name))
        assigned_counts: dict[str, int] = {agent.name: 0 for agent in sorted_agents}
        assignments: list[RoleAssignment] = []
        explanations: list[str] = []

        for profile in sorted(self._profiles, key=lambda item: (item.priority, item.role)):
            candidates = [
                agent
                for agent in sorted_agents
                if profile.required_capabilities.issubset(agent.capabilities)
            ]
            ranked = sorted(
                candidates,
                key=lambda agent: (
                    assigned_counts[agent.name],
                    -self.agent_score(agent.name).score,
                    len(agent.capabilities - profile.required_capabilities),
                    agent.name,
                ),
            )
            selected = ranked[: profile.max_agents]

            if not selected:
                explanations.append(
                    f"No agent assigned to {profile.role}; missing capabilities "
                    f"{sorted(profile.required_capabilities)}."
                )
                continue

            for agent in selected:
                assigned_counts[agent.name] += 1
                assignments.append(
                    RoleAssignment(
                        role=profile.role,
                        agent_name=agent.name,
                        capabilities=agent.capabilities,
                        priority=profile.priority,
                        reason=(
                            f"Assigned by capability match for "
                            f"{sorted(profile.required_capabilities)} with performance "
                            f"score {self.agent_score(agent.name).score:.3f}. {profile.reason}"
                        ).strip(),
                        performance_score=self.agent_score(agent.name).score,
                    )
                )
            explanations.append(
                f"Assigned {', '.join(agent.name for agent in selected)} to {profile.role}."
            )

        return tuple(assignments), tuple(explanations)

    def agent_score(self, agent_name: str) -> AgentScore:
        return self._scores.get(agent_name, AgentScore(agent_name=agent_name))

    def update_performance(
        self,
        agent_name: str,
        outcome: PerformanceOutcome,
        *,
        reason: str = "",
    ) -> PerformanceUpdate:
        current = self.agent_score(agent_name)
        deltas = {
            PerformanceOutcome.SUCCESS: 0.08,
            PerformanceOutcome.FAILURE: -0.12,
            PerformanceOutcome.TIMEOUT: -0.16,
            PerformanceOutcome.ROLLBACK: -0.2,
        }
        delta = deltas[outcome]
        next_score = min(1.0, max(0.0, current.score + delta))
        updated = AgentScore(
            agent_name=agent_name,
            score=next_score,
            successes=current.successes + (1 if outcome == PerformanceOutcome.SUCCESS else 0),
            failures=current.failures + (1 if outcome == PerformanceOutcome.FAILURE else 0),
            timeouts=current.timeouts + (1 if outcome == PerformanceOutcome.TIMEOUT else 0),
            rollbacks=current.rollbacks + (1 if outcome == PerformanceOutcome.ROLLBACK else 0),
        )
        self._scores[agent_name] = updated
        return PerformanceUpdate(
            agent_name=agent_name,
            outcome=outcome,
            delta=delta,
            score=next_score,
            reason=reason,
        )

    def scorecard(self) -> tuple[AgentScore, ...]:
        return tuple(sorted(self._scores.values(), key=lambda score: score.agent_name))

    def switch_roles(
        self,
        session: SwarmSession,
        agents: Sequence[AgentDescriptor],
    ) -> RoleSwitchResult:
        assignments, explanations = self.assign_roles(agents)
        replacements = self._replacement_map(session.assignments, assignments)
        changed = session.assignments != assignments
        next_session = SwarmSession(
            objective=session.objective,
            assignments=assignments,
            id=session.id,
            metadata=session.metadata,
            explanation=(
                *session.explanation,
                "Re-evaluated swarm roles using current performance scores.",
                *explanations,
            ),
        )
        return RoleSwitchResult(
            session=next_session,
            changed=changed,
            replacements=replacements,
            explanation=(
                "Role switch completed." if changed else "Role switch made no changes.",
                f"Replacements: {replacements or 'none'}.",
            ),
        )

    def replace_agent(
        self,
        session: SwarmSession,
        agent_name: str,
        agents: Sequence[AgentDescriptor],
        *,
        reason: str = "",
    ) -> RoleSwitchResult:
        remaining_agents = tuple(agent for agent in agents if agent.name != agent_name)
        current_roles = tuple(
            assignment.role for assignment in session.assignments if assignment.agent_name == agent_name
        )
        if not current_roles:
            return RoleSwitchResult(
                session=session,
                changed=False,
                replacements={},
                explanation=(f"Agent '{agent_name}' is not assigned in this session.",),
            )

        switched = self.switch_roles(session, remaining_agents)
        explanation = (
            f"Requested replacement for '{agent_name}' because: {reason or 'unspecified'}.",
            *switched.explanation,
        )
        return RoleSwitchResult(
            session=switched.session,
            changed=switched.changed,
            replacements=switched.replacements,
            explanation=explanation,
        )

    def replace_underperforming(
        self,
        session: SwarmSession,
        agents: Sequence[AgentDescriptor],
    ) -> RoleSwitchResult:
        weak_agents = {
            assignment.agent_name
            for assignment in session.assignments
            if self.agent_score(assignment.agent_name).score < self._minimum_replacement_score
        }
        if not weak_agents:
            return RoleSwitchResult(
                session=session,
                changed=False,
                replacements={},
                explanation=("No assigned agent is below the replacement threshold.",),
            )

        remaining_agents = tuple(agent for agent in agents if agent.name not in weak_agents)
        switched = self.switch_roles(session, remaining_agents)
        return RoleSwitchResult(
            session=switched.session,
            changed=switched.changed,
            replacements=switched.replacements,
            explanation=(
                f"Replacing underperforming agents below score "
                f"{self._minimum_replacement_score:.3f}: {sorted(weak_agents)}.",
                *switched.explanation,
            ),
        )

    def resolve_conflicts(self, proposals: Sequence[Proposal]) -> tuple[str, ...]:
        by_decision: dict[str, list[Proposal]] = {}
        for proposal in proposals:
            by_decision.setdefault(proposal.decision, []).append(proposal)
        if len(by_decision) <= 1:
            return ()
        return tuple(
            f"{decision}: {sorted(proposal.agent_name for proposal in proposal_group)}"
            for decision, proposal_group in sorted(by_decision.items())
        )

    def consensus(
        self,
        session: SwarmSession,
        proposals: Sequence[Proposal],
    ) -> ConsensusResult:
        trusted_proposals = self._filter_assigned_proposals(session, proposals)
        votes = tuple(self._proposal_to_vote(session, proposal) for proposal in trusted_proposals)
        conflicts = self.resolve_conflicts(trusted_proposals)

        if len(votes) < self._quorum:
            return ConsensusResult(
                status=ConsensusStatus.INSUFFICIENT_QUORUM,
                decision=None,
                score=0,
                quorum=self._quorum,
                votes=votes,
                conflicts=conflicts,
                explanation=(
                    f"Only {len(votes)} vote(s) available; quorum requires {self._quorum}.",
                ),
            )

        totals: dict[str, float] = {}
        for vote in votes:
            totals[vote.decision] = totals.get(vote.decision, 0) + vote.weight

        ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        winner, winning_score = ranked[0]
        total_score = sum(totals.values())
        normalized_score = winning_score / total_score if total_score else 0
        tied = len(ranked) > 1 and ranked[0][1] == ranked[1][1]

        if tied:
            status = ConsensusStatus.TIED
            decision = self._tie_break(session, votes, tied_decisions={ranked[0][0], ranked[1][0]})
            explanation = (
                "Consensus tied by weighted score.",
                f"Deterministic tie-break selected '{decision}' by role priority and agent name.",
            )
        elif normalized_score >= self._acceptance_threshold:
            status = ConsensusStatus.ACCEPTED
            decision = winner
            explanation = (
                f"Consensus accepted '{decision}' with normalized score "
                f"{normalized_score:.3f}.",
            )
        else:
            status = ConsensusStatus.REJECTED
            decision = winner
            explanation = (
                f"Top decision '{decision}' scored {normalized_score:.3f}, below "
                f"threshold {self._acceptance_threshold:.3f}.",
            )

        return ConsensusResult(
            status=status,
            decision=decision,
            score=normalized_score,
            quorum=self._quorum,
            votes=votes,
            conflicts=conflicts,
            explanation=(
                *explanation,
                f"Vote totals: {dict(sorted(totals.items()))}.",
                f"Conflicts: {conflicts or 'none'}.",
            ),
        )

    def explain_session(self, session: SwarmSession) -> tuple[str, ...]:
        lines = [f"Swarm {session.id}: {session.objective}.", *session.explanation]
        for assignment in session.assignments:
            lines.append(
                f"{assignment.role}: {assignment.agent_name}; "
                f"capabilities={sorted(assignment.capabilities)}; reason={assignment.reason}"
            )
        return tuple(lines)

    async def _resolve_agents(
        self,
        agents: Sequence[AgentDescriptor] | None,
    ) -> tuple[AgentDescriptor, ...]:
        if agents is not None:
            return tuple(sorted(agents, key=lambda agent: agent.name))
        if self._agent_registry is None:
            return ()
        return await self._agent_registry.descriptors()

    def _filter_assigned_proposals(
        self,
        session: SwarmSession,
        proposals: Sequence[Proposal],
    ) -> tuple[Proposal, ...]:
        assigned = {(assignment.agent_name, assignment.role) for assignment in session.assignments}
        return tuple(
            sorted(
                (
                    proposal
                    for proposal in proposals
                    if (proposal.agent_name, proposal.role) in assigned
                ),
                key=lambda proposal: (proposal.decision, proposal.role, proposal.agent_name),
            )
        )

    def _proposal_to_vote(self, session: SwarmSession, proposal: Proposal) -> Vote:
        assignment = self._assignment_for(session, proposal.agent_name, proposal.role)
        role_weight = 1 / assignment.priority
        confidence_weight = max(proposal.confidence, 0)
        return Vote(
            agent_name=proposal.agent_name,
            role=proposal.role,
            decision=proposal.decision,
            weight=role_weight * confidence_weight * self.agent_score(proposal.agent_name).score,
            rationale=proposal.rationale,
        )

    def _assignment_for(
        self,
        session: SwarmSession,
        agent_name: str,
        role: SwarmRole,
    ) -> RoleAssignment:
        for assignment in session.assignments:
            if assignment.agent_name == agent_name and assignment.role == role:
                return assignment
        raise KeyError(f"agent {agent_name} is not assigned to role {role}")

    def _tie_break(
        self,
        session: SwarmSession,
        votes: Sequence[Vote],
        *,
        tied_decisions: set[str],
    ) -> str:
        candidates = [vote for vote in votes if vote.decision in tied_decisions]
        ranked = sorted(
            candidates,
            key=lambda vote: (
                self._assignment_for(session, vote.agent_name, vote.role).priority,
                vote.role,
                vote.agent_name,
                vote.decision,
            ),
        )
        return ranked[0].decision

    def _replacement_map(
        self,
        previous: Sequence[RoleAssignment],
        current: Sequence[RoleAssignment],
    ) -> dict[str, str]:
        previous_by_role = self._agents_by_role(previous)
        current_by_role = self._agents_by_role(current)
        replacements: dict[str, str] = {}
        for role in sorted(set(previous_by_role) | set(current_by_role)):
            previous_agents = previous_by_role.get(role, ())
            current_agents = current_by_role.get(role, ())
            removed = [agent for agent in previous_agents if agent not in current_agents]
            added = [agent for agent in current_agents if agent not in previous_agents]
            for old, new in zip(sorted(removed), sorted(added), strict=False):
                replacements[f"{role}:{old}"] = new
        return replacements

    def _agents_by_role(
        self,
        assignments: Sequence[RoleAssignment],
    ) -> dict[SwarmRole, tuple[str, ...]]:
        grouped: dict[SwarmRole, list[str]] = {}
        for assignment in assignments:
            grouped.setdefault(assignment.role, []).append(assignment.agent_name)
        return {
            role: tuple(sorted(agent_names))
            for role, agent_names in grouped.items()
        }


def default_role_profiles() -> tuple[RoleProfile, ...]:
    return (
        RoleProfile(
            role=SwarmRole.COORDINATOR,
            required_capabilities=frozenset({"swarm.coordinate"}),
            priority=1,
            reason="Coordinator owns collaboration flow.",
        ),
        RoleProfile(
            role=SwarmRole.INVESTIGATOR,
            required_capabilities=frozenset({"telemetry.read"}),
            priority=2,
            max_agents=2,
            reason="Investigators gather and compare evidence.",
        ),
        RoleProfile(
            role=SwarmRole.PLANNER,
            required_capabilities=frozenset({"reason.plan"}),
            priority=3,
            reason="Planner decomposes proposed action.",
        ),
        RoleProfile(
            role=SwarmRole.VERIFIER,
            required_capabilities=frozenset({"verify.result"}),
            priority=4,
            reason="Verifier checks assumptions and outcomes.",
        ),
        RoleProfile(
            role=SwarmRole.EXECUTOR,
            required_capabilities=frozenset({"execute.safe"}),
            priority=5,
            reason="Executor performs approved work only.",
        ),
    )
