from __future__ import annotations

from anubis.types import EventType

from core.bootstrap import UltraLightBootstrapConfig, start_ultra_light_bootstrap
from core.graph import GraphOrchestrator
from core.memory import MemoryManager


async def test_ultra_light_bootstrap_starts_only_core_services() -> None:
    runtime = await start_ultra_light_bootstrap(
        UltraLightBootstrapConfig(source="test_ultra_light")
    )
    payload = runtime.to_dict()

    assert payload["system"] == "ANUBIS"
    assert payload["mode"] == "ultra_light"
    assert payload["started"] is True
    assert payload["modules"] == ("event_bus", "memory", "orchestrator")
    assert isinstance(runtime.memory, MemoryManager)
    assert isinstance(runtime.orchestrator, GraphOrchestrator)
    assert runtime.orchestrator.run_count == 0
    assert payload["memory"]["append_only"] is True


async def test_ultra_light_bootstrap_publishes_start_event() -> None:
    runtime = await start_ultra_light_bootstrap()
    events = runtime.event_bus.events

    assert len(events) == 1
    assert events[0].type == EventType.LIFE_LOOP_STARTED
    assert events[0].payload["mode"] == "ultra_light"
    assert events[0].payload["execution_started"] is False


async def test_ultra_light_bootstrap_can_disable_start_event() -> None:
    runtime = await start_ultra_light_bootstrap(
        UltraLightBootstrapConfig(publish_start_event=False)
    )

    assert runtime.event_bus.events == ()
    assert runtime.to_dict()["event_count"] == 0
