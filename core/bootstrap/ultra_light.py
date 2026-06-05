"""Ultra-light bootstrap for ANUBIS core services.

This module intentionally starts only the minimum local runtime surface:

1. event bus
2. memory manager
3. core graph orchestrator facade

It does not execute user tasks, load plugins, enable network access, or run the
full bootstrap pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anubis.events import InMemoryEventBus
from anubis.types import Event, EventType

from core.graph import GraphOrchestrator
from core.memory import MemoryManager


@dataclass(frozen=True, slots=True)
class UltraLightBootstrapConfig:
    source: str = "ultra_light_bootstrap"
    publish_start_event: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", self.source.strip() or "ultra_light_bootstrap")


@dataclass(frozen=True, slots=True)
class UltraLightRuntime:
    """Minimal ANUBIS runtime handle."""

    event_bus: InMemoryEventBus
    memory: MemoryManager
    orchestrator: GraphOrchestrator
    started: bool
    modules: tuple[str, ...] = field(
        default=(
            "event_bus",
            "memory",
            "orchestrator",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": "ANUBIS",
            "mode": "ultra_light",
            "started": self.started,
            "modules": self.modules,
            "event_count": len(self.event_bus.events),
            "memory": self.memory.snapshot(),
            "orchestrator": {
                "type": type(self.orchestrator).__name__,
                "loaded": True,
                "run_count": self.orchestrator.run_count,
            },
        }


async def start_ultra_light_bootstrap(
    config: UltraLightBootstrapConfig | None = None,
) -> UltraLightRuntime:
    """Start only the ANUBIS core control primitives."""

    active_config = config or UltraLightBootstrapConfig()
    event_bus = InMemoryEventBus()
    memory = MemoryManager()
    orchestrator = GraphOrchestrator.build()

    if active_config.publish_start_event:
        await event_bus.publish(
            Event(
                type=EventType.LIFE_LOOP_STARTED,
                producer=active_config.source,
                payload={
                    "mode": "ultra_light",
                    "modules": ("event_bus", "memory", "orchestrator"),
                    "execution_started": False,
                },
            )
        )

    return UltraLightRuntime(
        event_bus=event_bus,
        memory=memory,
        orchestrator=orchestrator,
        started=True,
    )


__all__ = [
    "UltraLightBootstrapConfig",
    "UltraLightRuntime",
    "start_ultra_light_bootstrap",
]
