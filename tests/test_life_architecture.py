from __future__ import annotations

from pathlib import Path

from anubis import (
    ArchitectureAnalyzer,
    Event,
    EventType,
    InMemoryEventBus,
    PatchGenerationEngine,
    PerformanceAnalyzer,
    UpgradePlanner,
)
from anubis.agents_life.thinker_agent import ThinkerAgent
from anubis.api_body.neural_api import NeuralAPI
from anubis.core_life.brain.intent_inference import IntentInference
from anubis.core_life.evolution.experiment_runner import ExperimentResult, ExperimentRunner
from anubis.life_cycle.boot_sequence import boot
from anubis.observability.introspection_dashboard import AgentActivityDashboard, AgentActivityRow
from anubis.types import Task


async def test_life_architecture_imports_and_boots() -> None:
    orchestrator = boot()
    agent = ThinkerAgent("thinker")
    result = await agent.handle(Task("think"))
    goal = NeuralAPI(IntentInference()).ingest("inspect alert")
    best = ExperimentRunner().choose_best(
        (
            ExperimentResult("a", 0.5),
            ExperimentResult("b", 0.7),
        )
    )
    dashboard = AgentActivityDashboard(
        rows=(AgentActivityRow(agent_name="thinker", status="idle", active_tasks=0),)
    )

    assert orchestrator is not None
    assert result.output["agent"] == "thinker"
    assert goal.objective == "inspect alert"
    assert best is not None and best.name == "b"
    assert dashboard.rows[0].agent_name == "thinker"


async def test_self_improvement_loop_generates_patch_only(tmp_path: Path) -> None:
    bus = InMemoryEventBus()
    path = tmp_path / "module.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    await bus.publish(
        Event(
            type=EventType.ARCHITECTURE_FINDING_CREATED,
            producer="test",
            payload={},
        )
    )

    performance = await PerformanceAnalyzer(event_bus=bus).analyze_events(bus.events)
    planner = UpgradePlanner(
        architecture_analyzer=ArchitectureAnalyzer(event_bus=bus),
        event_bus=bus,
    )
    proposal = (await planner.propose_upgrades(performance_report=performance, paths=(path,)))[0]
    result = await PatchGenerationEngine(event_bus=bus).apply_safe(proposal)

    assert result.applied is False
    assert result.changed_files == ()
    assert result.requires_human_approval is True
    assert result.patch.startswith("diff --git")
    assert path.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert EventType.SELF_PERFORMANCE_ANALYZED in [event.type for event in bus.events]
    assert EventType.SELF_UPGRADE_PROPOSED in [event.type for event in bus.events]
    assert EventType.SELF_UPGRADE_SIMULATED in [event.type for event in bus.events]
    assert EventType.PATCH_PROPOSED in [event.type for event in bus.events]
    assert EventType.PATCH_REQUIRES_APPROVAL in [event.type for event in bus.events]
