from __future__ import annotations

import asyncio

from anubis import Event, EventType, InMemoryEventBus, ReplayPosition


async def test_publish_persists_and_delivers_to_typed_subscribers() -> None:
    bus = InMemoryEventBus()
    received: list[EventType] = []

    async def handler(event: Event) -> None:
        received.append(event.type)

    bus.subscribe(EventType.TASK_SUBMITTED, handler)

    await bus.publish(Event(EventType.TASK_SUBMITTED, "test", {"x": 1}))
    await bus.publish(Event(EventType.TASK_STARTED, "test", {"x": 2}))

    assert received == [EventType.TASK_SUBMITTED]
    assert [stored.event.type for stored in await bus.replay()] == [
        EventType.TASK_SUBMITTED,
        EventType.TASK_STARTED,
    ]


async def test_wildcard_subscriber_receives_all_events_in_publish_order() -> None:
    bus = InMemoryEventBus()
    received: list[EventType] = []

    async def handler(event: Event) -> None:
        received.append(event.type)

    bus.subscribe(None, handler)

    await bus.publish(Event(EventType.TASK_SUBMITTED, "test", {}))
    await bus.publish(Event(EventType.TASK_STARTED, "test", {}))

    assert received == [EventType.TASK_SUBMITTED, EventType.TASK_STARTED]


async def test_replay_after_sequence_filters_events() -> None:
    bus = InMemoryEventBus()
    await bus.publish(Event(EventType.TASK_SUBMITTED, "test", {}))
    await bus.publish(Event(EventType.TASK_STARTED, "test", {}))
    await bus.publish(Event(EventType.TASK_SUCCEEDED, "test", {}))

    replayed = await bus.replay(after_sequence=1, limit=1)

    assert len(replayed) == 1
    assert replayed[0].sequence == 2
    assert replayed[0].event.type == EventType.TASK_STARTED


async def test_subscribe_can_replay_existing_events_from_beginning() -> None:
    bus = InMemoryEventBus()
    received: list[EventType] = []

    await bus.publish(Event(EventType.TASK_SUBMITTED, "test", {}))
    await bus.publish(Event(EventType.TASK_STARTED, "test", {}))

    async def handler(event: Event) -> None:
        received.append(event.type)

    bus.subscribe(None, handler, replay=ReplayPosition.BEGINNING)
    await asyncio.sleep(0)

    assert received == [EventType.TASK_SUBMITTED, EventType.TASK_STARTED]


async def test_handler_failure_is_isolated_in_dead_letter_queue() -> None:
    bus = InMemoryEventBus()
    received: list[EventType] = []

    async def bad_handler(_: Event) -> None:
        raise RuntimeError("handler broke")

    async def good_handler(event: Event) -> None:
        received.append(event.type)

    bus.subscribe(EventType.TASK_SUBMITTED, bad_handler)
    bus.subscribe(EventType.TASK_SUBMITTED, good_handler)

    await bus.publish(Event(EventType.TASK_SUBMITTED, "test", {}))

    assert received == [EventType.TASK_SUBMITTED]
    assert len(bus.dead_letters) == 1
    assert bus.dead_letters[0].error == "handler broke"

