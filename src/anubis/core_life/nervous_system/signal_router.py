"""Signal routing over the ANUBIS event bus."""

from dataclasses import dataclass

from anubis.events import EventBus
from anubis.types import Event


@dataclass(slots=True)
class SignalRouter:
    event_bus: EventBus

    async def route(self, event: Event) -> None:
        await self.event_bus.publish(event)

