from pathlib import Path

from anubis import (
    ArchitectureMutator,
    Event,
    EventType,
    EvolutionEngine,
    EvolutionPolicy,
    FitnessFunction,
    InMemoryEventBus,
    VersionControlTree,
    build_runtime,
)
from anubis.api_body.stimulus_input import StimulusInput
from anubis.self_improvement import PerformanceAnalyzer


def test_fitness_function_scores_runtime_health_deterministically():
    events = (
        Event(type=EventType.TASK_SUCCEEDED, producer="test", payload={}),
        Event(type=EventType.EXECUTION_RETRY_SCHEDULED, producer="test", payload={}),
        Event(type=EventType.TASK_FAILED, producer="test", payload={}),
    )

    score = FitnessFunction().evaluate(events)

    assert score.task_success_rate == 0.5
    assert 0 <= score.total <= 1
    assert score.as_dict()["total"] == score.total


async def test_evolution_engine_simulates_candidates_and_versions_tree(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    tree_path = tmp_path / "versioning_tree.json"
    bus = InMemoryEventBus()
    await bus.publish(Event(type=EventType.TASK_SUCCEEDED, producer="test", payload={}))

    engine = EvolutionEngine(
        policy=EvolutionPolicy(enabled=True, approved_paths=(str(tmp_path),)),
        architecture_mutator=ArchitectureMutator(),
        performance_analyzer=PerformanceAnalyzer(event_bus=bus),
        version_tree=VersionControlTree(storage_path=tree_path),
        event_bus=bus,
    )

    result = await engine.evolve(events=bus.events, paths=(target,))

    assert result.enabled is True
    assert result.mutation_plan is not None
    assert result.simulations
    assert result.genome_versions
    assert tree_path.exists()
    assert EventType.EVOLUTION_VERSION_CREATED in [event.type for event in bus.events]
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


async def test_evolution_generates_review_only_versions(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    bus = InMemoryEventBus()

    engine = EvolutionEngine(
        policy=EvolutionPolicy(
            enabled=True,
            approved_paths=(str(tmp_path),),
        ),
        event_bus=bus,
    )

    result = await engine.evolve(events=(), paths=(target,))

    assert result.genome_versions
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


async def test_evolution_policy_blocks_forbidden_paths(tmp_path: Path):
    protected = tmp_path / "bootstrap.py"
    protected.write_text("VALUE = 1\n", encoding="utf-8")
    bus = InMemoryEventBus()

    engine = EvolutionEngine(
        policy=EvolutionPolicy(
            enabled=True,
            approved_paths=(str(tmp_path),),
            forbidden_paths=(str(protected),),
        ),
        event_bus=bus,
    )

    result = await engine.evolve(events=(), paths=(protected,))

    assert result.rejected
    assert EventType.EVOLUTION_POLICY_REJECTED in [event.type for event in bus.events]


async def test_runtime_runs_with_evolution_disabled_by_default():
    runtime = await build_runtime()
    result = await runtime.cognitive_loop.run(StimulusInput("Investigate local drift", source="test"))

    assert result.succeeded
    assert result.evolution is not None
    assert result.evolution.enabled is False
    assert result.upgrade_proposals == ()
