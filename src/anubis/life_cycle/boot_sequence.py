"""System birth sequence."""

from dataclasses import dataclass
from pathlib import Path

from agents import AnalystAgent, CriticAgent, PlannerAgent, ResearchExecutorAgent, SynthesizerAgent
from anubis.agents_life.base_living_agent import BaseLivingAgent
from anubis.agents_life.executor_agent import ExecutorAgent
from anubis.agents_life.healer_agent import HealerAgent
from anubis.agents_life.predator_agent import PredatorAgent
from anubis.agents_life.thinker_agent import ThinkerAgent
from anubis.agents_life.watcher_agent import WatcherAgent
from anubis.core_life.evolution.self_refactor_engine import EvolutionEngine, EvolutionPolicy
from anubis.core_life.evolution.version_control_tree import VersionControlTree
from anubis.core_life.living_loop import PrincipalLoop
from anubis.core_life.memory_life.episodic_memory import EpisodicMemory
from anubis.core_life.memory_life.semantic_memory import SemanticMemory
from anubis.core_life.swarm import HiveMind, ResearchAgentRegistry, SwarmMemory
from anubis.events import InMemoryEventBus
from anubis.execution import ExecutionLayer, ExecutionPolicy, RetryPolicy
from anubis.observability.consciousness_logger import ConsciousnessLogger
from anubis.orchestrator import Orchestrator
from anubis.sandbox import CapabilityGrant, PermissionSet, PermissionSystem, default_sandbox
from anubis.types import Event


def boot() -> Orchestrator:
    return Orchestrator(event_bus=InMemoryEventBus())


@dataclass(slots=True)
class AnubisRuntime:
    event_bus: InMemoryEventBus
    orchestrator: Orchestrator
    cognitive_loop: PrincipalLoop
    episodic_memory: EpisodicMemory
    semantic_memory: SemanticMemory
    logger: ConsciousnessLogger
    agents: tuple[BaseLivingAgent, ...]
    evolution_engine: EvolutionEngine | None = None
    research_hive: HiveMind | None = None


async def build_runtime(
    *,
    evolution_enabled: bool = False,
    evolution_tree_path: str | Path | None = None,
) -> AnubisRuntime:
    event_bus = InMemoryEventBus()
    logger = ConsciousnessLogger()
    event_bus.subscribe(None, _log_event(logger))

    agents: tuple[BaseLivingAgent, ...] = (
        WatcherAgent(),
        ThinkerAgent(),
        ExecutorAgent(),
        HealerAgent(),
        PredatorAgent(),
    )
    permission_system = PermissionSystem(
        tuple(
            PermissionSet(
                agent_name=agent.name,
                grants=frozenset(CapabilityGrant(capability) for capability in agent.capabilities),
            )
            for agent in agents
        )
    )
    sandbox = default_sandbox()
    sandbox.permissions = permission_system

    orchestrator = Orchestrator(
        event_bus=event_bus,
        execution_layer=ExecutionLayer(
            event_bus=event_bus,
            sandbox=sandbox,
            policy=ExecutionPolicy(
                retry=RetryPolicy(max_attempts=2, backoff_seconds=0),
                timeout_seconds=5,
            ),
        ),
    )
    for agent in agents:
        await orchestrator.register_agent(agent.descriptor(), agent.handle)

    episodic_memory = EpisodicMemory()
    semantic_memory = SemanticMemory()
    semantic_memory.remember(
        "ANUBIS is a local-first autonomous defense system with explainable agent routing.",
        owner_id="system",
    )
    research_registry = ResearchAgentRegistry()
    for research_agent in (
        PlannerAgent(),
        ResearchExecutorAgent(),
        AnalystAgent(),
        CriticAgent(),
        SynthesizerAgent(),
    ):
        research_registry.register(research_agent)
    research_hive = HiveMind(
        registry=research_registry,
        memory=SwarmMemory(),
        event_bus=event_bus,
    )

    evolution_engine = EvolutionEngine(
        policy=EvolutionPolicy(enabled=evolution_enabled),
        version_tree=VersionControlTree(storage_path=evolution_tree_path),
        event_bus=event_bus,
    )

    cognitive_loop = PrincipalLoop(
        orchestrator=orchestrator,
        event_bus=event_bus,
        episodic_memory=episodic_memory,
        evolution_engine=evolution_engine,
        evolution_paths=("src/anubis/agents_life", "src/anubis/core_life/evolution"),
    )

    return AnubisRuntime(
        event_bus=event_bus,
        orchestrator=orchestrator,
        cognitive_loop=cognitive_loop,
        episodic_memory=episodic_memory,
        semantic_memory=semantic_memory,
        logger=logger,
        agents=agents,
        evolution_engine=evolution_engine,
        research_hive=research_hive,
    )


def _log_event(logger: ConsciousnessLogger):
    async def handler(event: Event) -> None:
        logger.log(
            "info",
            event.type.value,
            component=event.producer,
            event_id=event.id,
            task_id=event.task_id,
            agent_name=event.agent_name,
            payload=dict(event.payload),
        )

    return handler
