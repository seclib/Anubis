import asyncio
import time
import unittest

from anubis.distributed import EventBus, EventType, OrchestrationEvent


def make_event(event_type: EventType, task_id: str = "task-1") -> OrchestrationEvent:
    return OrchestrationEvent(
        event_type=event_type,
        task_id=task_id,
        message=event_type.value,
    )


class PhaseB5EventBusTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        if hasattr(self, "bus"):
            await self.bus.drain()
            self.bus.close()

    async def test_publish_routes_to_event_type_subscribers(self) -> None:
        self.bus = EventBus()
        received: list[EventType] = []

        self.bus.subscribe(EventType.TASK_CREATED, lambda event: received.append(event.event_type))
        self.bus.publish(make_event(EventType.TASK_ASSIGNED))
        self.bus.publish(make_event(EventType.TASK_CREATED))
        await self.bus.drain()

        self.assertEqual(received, [EventType.TASK_CREATED])

    async def test_wildcard_subscriber_receives_all_required_event_types(self) -> None:
        self.bus = EventBus()
        received: list[EventType] = []
        required = (
            EventType.TASK_CREATED,
            EventType.TASK_ASSIGNED,
            EventType.STEP_STARTED,
            EventType.STEP_COMPLETED,
            EventType.STEP_FAILED,
            EventType.TASK_COMPLETED,
        )

        self.bus.subscribe(None, lambda event: received.append(event.event_type))
        for event_type in required:
            self.bus.publish(make_event(event_type))
        await self.bus.drain()

        self.assertEqual(received, list(required))

    async def test_async_handlers_are_non_blocking(self) -> None:
        self.bus = EventBus()
        received: list[str] = []

        async def handler(event: OrchestrationEvent) -> None:
            await asyncio.sleep(0.05)
            received.append(event.task_id)

        self.bus.subscribe(EventType.STEP_STARTED, handler)
        started = time.perf_counter()
        self.bus.publish(make_event(EventType.STEP_STARTED))
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.02)
        self.assertEqual(received, [])
        await self.bus.drain()
        self.assertEqual(received, ["task-1"])

    async def test_concurrent_agents_can_handle_same_event(self) -> None:
        self.bus = EventBus()
        received: list[str] = []

        async def slow_handler(event: OrchestrationEvent) -> None:
            await asyncio.sleep(0.05)
            received.append(f"slow:{event.task_id}")

        async def fast_handler(event: OrchestrationEvent) -> None:
            await asyncio.sleep(0.01)
            received.append(f"fast:{event.task_id}")

        self.bus.subscribe(EventType.STEP_COMPLETED, slow_handler)
        self.bus.subscribe(EventType.STEP_COMPLETED, fast_handler)

        started = time.perf_counter()
        self.bus.publish(make_event(EventType.STEP_COMPLETED))
        await self.bus.drain()
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.08)
        self.assertEqual(set(received), {"slow:task-1", "fast:task-1"})

    async def test_publish_stores_event_history(self) -> None:
        self.bus = EventBus()
        event = make_event(EventType.STEP_FAILED)

        self.bus.publish(event)

        self.assertEqual(self.bus.events(), (event,))

    async def test_legacy_subscribe_order_remains_supported(self) -> None:
        self.bus = EventBus()
        received: list[str] = []

        self.bus.subscribe(lambda event: received.append(event.message), EventType.TASK_COMPLETED)
        self.bus.publish(make_event(EventType.TASK_COMPLETED))
        await self.bus.drain()

        self.assertEqual(received, ["task_completed"])


if __name__ == "__main__":
    unittest.main()
