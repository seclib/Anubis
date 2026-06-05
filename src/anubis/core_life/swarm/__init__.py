"""Autonomous research swarm subsystem."""

from anubis.core_life.swarm.agent_registry import (
    AgentInsight,
    ResearchAgent,
    ResearchAgentDescriptor,
    ResearchAgentRegistry,
    ResearchRole,
    ResearchTask,
)
from anubis.core_life.swarm.consensus_engine import ConsensusEngine, ConsensusOutcome, SwarmVote
from anubis.core_life.swarm.hive_mind import HiveMind, SwarmResearchResult
from anubis.core_life.swarm.role_allocator import RoleAllocation, RoleAllocator
from anubis.core_life.swarm.swarm_memory import SwarmMemory

__all__ = [
    "AgentInsight",
    "ConsensusEngine",
    "ConsensusOutcome",
    "HiveMind",
    "ResearchAgent",
    "ResearchAgentDescriptor",
    "ResearchAgentRegistry",
    "ResearchRole",
    "ResearchTask",
    "RoleAllocation",
    "RoleAllocator",
    "SwarmMemory",
    "SwarmResearchResult",
    "SwarmVote",
]
