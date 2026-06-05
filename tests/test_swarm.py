from __future__ import annotations

from anubis import (
    AgentDescriptor,
    ConsensusStatus,
    PerformanceOutcome,
    Proposal,
    SwarmCoordinator,
    SwarmRole,
)


async def test_assigns_roles_by_capability_and_load_balances_deterministically() -> None:
    swarm = SwarmCoordinator()

    session = await swarm.create_session(
        "triage incident",
        agents=(
            AgentDescriptor("z-wide", frozenset({"telemetry.read", "reason.plan"})),
            AgentDescriptor("a-coordinator", frozenset({"swarm.coordinate"})),
            AgentDescriptor("b-investigator", frozenset({"telemetry.read"})),
            AgentDescriptor("c-planner", frozenset({"reason.plan"})),
            AgentDescriptor("d-verifier", frozenset({"verify.result"})),
            AgentDescriptor("e-executor", frozenset({"execute.safe"})),
        ),
    )

    assert session.agents_for_role(SwarmRole.COORDINATOR) == ("a-coordinator",)
    assert session.agents_for_role(SwarmRole.INVESTIGATOR) == (
        "b-investigator",
        "z-wide",
    )
    assert session.agents_for_role(SwarmRole.PLANNER) == ("c-planner",)
    assert session.agents_for_role(SwarmRole.VERIFIER) == ("d-verifier",)
    assert session.agents_for_role(SwarmRole.EXECUTOR) == ("e-executor",)


async def test_consensus_accepts_weighted_majority() -> None:
    swarm = SwarmCoordinator(quorum=2)
    session = await swarm.create_session(
        "decide containment",
        agents=(
            AgentDescriptor("coord", frozenset({"swarm.coordinate"})),
            AgentDescriptor("investigator", frozenset({"telemetry.read"})),
            AgentDescriptor("planner", frozenset({"reason.plan"})),
        ),
    )

    result = swarm.consensus(
        session,
        (
            Proposal("coord", SwarmRole.COORDINATOR, "contain", 0.8, "high risk"),
            Proposal("investigator", SwarmRole.INVESTIGATOR, "contain", 0.7, "matches evidence"),
            Proposal("planner", SwarmRole.PLANNER, "monitor", 0.9, "avoid disruption"),
        ),
    )

    assert result.status == ConsensusStatus.ACCEPTED
    assert result.decision == "contain"
    assert result.conflicts


async def test_consensus_rejects_unassigned_proposals_and_requires_quorum() -> None:
    swarm = SwarmCoordinator(quorum=2)
    session = await swarm.create_session(
        "decide containment",
        agents=(AgentDescriptor("coord", frozenset({"swarm.coordinate"})),),
    )

    result = swarm.consensus(
        session,
        (
            Proposal("coord", SwarmRole.COORDINATOR, "monitor", 0.9, "limited evidence"),
            Proposal("intruder", SwarmRole.PLANNER, "contain", 1.0, "not assigned"),
        ),
    )

    assert result.status == ConsensusStatus.INSUFFICIENT_QUORUM
    assert result.decision is None
    assert len(result.votes) == 1


async def test_consensus_tie_breaks_by_role_priority() -> None:
    swarm = SwarmCoordinator(quorum=2)
    session = await swarm.create_session(
        "decide containment",
        agents=(
            AgentDescriptor("coord", frozenset({"swarm.coordinate"})),
            AgentDescriptor("investigator", frozenset({"telemetry.read"})),
        ),
    )

    result = swarm.consensus(
        session,
        (
            Proposal("coord", SwarmRole.COORDINATOR, "contain", 0.5, "coordinator view"),
            Proposal("investigator", SwarmRole.INVESTIGATOR, "monitor", 1.0, "evidence view"),
        ),
    )

    assert result.status == ConsensusStatus.TIED
    assert result.decision == "contain"
    assert "tie-break selected 'contain'" in result.explanation[1]


async def test_performance_updates_change_scorecard() -> None:
    swarm = SwarmCoordinator()

    update = swarm.update_performance(
        "agent",
        PerformanceOutcome.SUCCESS,
        reason="completed verification",
    )
    update = swarm.update_performance(
        "agent",
        PerformanceOutcome.TIMEOUT,
        reason="missed deadline",
    )

    score = swarm.agent_score("agent")

    assert update.score == score.score
    assert score.successes == 1
    assert score.timeouts == 1
    assert round(score.score, 2) == 0.42


async def test_dynamic_role_switch_prefers_higher_performance_agent() -> None:
    swarm = SwarmCoordinator()
    agents = (
        AgentDescriptor("primary", frozenset({"swarm.coordinate"})),
        AgentDescriptor("backup", frozenset({"swarm.coordinate"})),
    )
    session = await swarm.create_session("coordinate", agents=agents)
    assert session.agents_for_role(SwarmRole.COORDINATOR) == ("backup",)

    swarm.update_performance("primary", PerformanceOutcome.SUCCESS)
    swarm.update_performance("primary", PerformanceOutcome.SUCCESS)
    switched = swarm.switch_roles(session, agents)

    assert switched.changed is True
    assert switched.session.agents_for_role(SwarmRole.COORDINATOR) == ("primary",)
    assert switched.replacements == {"coordinator:backup": "primary"}


async def test_replace_agent_removes_unavailable_assignment() -> None:
    swarm = SwarmCoordinator()
    agents = (
        AgentDescriptor("coord-a", frozenset({"swarm.coordinate"})),
        AgentDescriptor("coord-b", frozenset({"swarm.coordinate"})),
    )
    session = await swarm.create_session("coordinate", agents=agents)

    replaced = swarm.replace_agent(
        session,
        "coord-a",
        agents,
        reason="health check failed",
    )

    assert replaced.changed is True
    assert replaced.session.agents_for_role(SwarmRole.COORDINATOR) == ("coord-b",)
    assert replaced.replacements == {"coordinator:coord-a": "coord-b"}


async def test_replace_underperforming_uses_threshold() -> None:
    swarm = SwarmCoordinator(minimum_replacement_score=0.4)
    agents = (
        AgentDescriptor("coord-a", frozenset({"swarm.coordinate"})),
        AgentDescriptor("coord-b", frozenset({"swarm.coordinate"})),
    )
    session = await swarm.create_session("coordinate", agents=agents)

    for _ in range(3):
        swarm.update_performance("coord-a", PerformanceOutcome.ROLLBACK)

    replaced = swarm.replace_underperforming(session, agents)

    assert replaced.changed is True
    assert replaced.session.agents_for_role(SwarmRole.COORDINATOR) == ("coord-b",)


async def test_consensus_weights_include_performance_score() -> None:
    swarm = SwarmCoordinator(quorum=2)
    session = await swarm.create_session(
        "decide",
        agents=(
            AgentDescriptor("coord", frozenset({"swarm.coordinate"})),
            AgentDescriptor("investigator", frozenset({"telemetry.read"})),
        ),
    )
    for _ in range(3):
        swarm.update_performance("coord", PerformanceOutcome.FAILURE)
    for _ in range(3):
        swarm.update_performance("investigator", PerformanceOutcome.SUCCESS)

    result = swarm.consensus(
        session,
        (
            Proposal("coord", SwarmRole.COORDINATOR, "contain", 1.0, "priority role"),
            Proposal("investigator", SwarmRole.INVESTIGATOR, "monitor", 1.0, "better record"),
        ),
    )

    assert result.status == ConsensusStatus.ACCEPTED
    assert result.decision == "monitor"
