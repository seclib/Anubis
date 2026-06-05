from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import DefaultDict

from anubis.types import Event, EventType

EventHandler = Callable[[Event], Awaitable[None]]


class ReplayPosition(StrEnum):
    BEGINNING = "beginning"
    LATEST = "latest"


@dataclass(frozen=True, slots=True)
class StoredEvent:
    sequence: int
    event: Event


@dataclass(frozen=True, slots=True)
class DeadLetter:
    event: Event
    handler_name: str
    error: str


@dataclass(frozen=True, slots=True)
class Subscription:
    id: str
    event_type: EventType | None
    handler: EventHandler


class EventStore:
    async def append(self, event: Event) -> StoredEvent:
        raise NotImplementedError

    async def replay(
        self,
        *,
        after_sequence: int = 0,
        event_type: EventType | None = None,
        limit: int | None = None,
    ) -> tuple[StoredEvent, ...]:
        raise NotImplementedError

    async def latest_sequence(self) -> int:
        raise NotImplementedError


class InMemoryEventStore(EventStore):
    """Append-only event persistence for local and test deployments."""

    def __init__(self) -> None:
        self._events: list[StoredEvent] = []
        self._next_sequence = 1
        self._lock = asyncio.Lock()

    async def append(self, event: Event) -> StoredEvent:
        async with self._lock:
            stored = StoredEvent(sequence=self._next_sequence, event=event)
            self._events.append(stored)
            self._next_sequence += 1
            return stored

    async def replay(
        self,
        *,
        after_sequence: int = 0,
        event_type: EventType | None = None,
        limit: int | None = None,
    ) -> tuple[StoredEvent, ...]:
        async with self._lock:
            matched = [
                stored
                for stored in self._events
                if stored.sequence > after_sequence
                and (event_type is None or stored.event.type == event_type)
            ]
            if limit is not None:
                matched = matched[:limit]
            return tuple(matched)

    async def latest_sequence(self) -> int:
        async with self._lock:
            return self._next_sequence - 1


class EventBus:
    async def publish(self, event: Event) -> None:
        raise NotImplementedError

    async def replay(
        self,
        *,
        after_sequence: int = 0,
        event_type: EventType | None = None,
        limit: int | None = None,
    ) -> tuple[StoredEvent, ...]:
        raise NotImplementedError

    def subscribe(
        self,
        event_type: EventType | None,
        handler: EventHandler,
        *,
        replay: ReplayPosition | int = ReplayPosition.LATEST,
    ) -> str:
        raise NotImplementedError

    def unsubscribe(self, subscription_id: str) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """Local event bus for tests and single-process deployments."""

    def __init__(self, *, store: EventStore | None = None) -> None:
        self._store = store or InMemoryEventStore()
        self._subscriptions: dict[str, Subscription] = {}
        self._by_type: DefaultDict[EventType | None, set[str]] = defaultdict(set)
        self._dead_letters: list[DeadLetter] = []
        self._lock = asyncio.Lock()
        self._next_subscription = 1

    @property
    def events(self) -> tuple[Event, ...]:
        if isinstance(self._store, InMemoryEventStore):
            return tuple(stored.event for stored in self._store._events)
        return ()

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        return tuple(self._dead_letters)

    async def publish(self, event: Event) -> None:
        stored = await self._store.append(event)
        async with self._lock:
            subscriptions = self._subscriptions_for(event.type)

        await self._deliver(stored.event, subscriptions)

    async def replay(
        self,
        *,
        after_sequence: int = 0,
        event_type: EventType | None = None,
        limit: int | None = None,
    ) -> tuple[StoredEvent, ...]:
        return await self._store.replay(
            after_sequence=after_sequence,
            event_type=event_type,
            limit=limit,
        )

    def subscribe(
        self,
        event_type: EventType | None,
        handler: EventHandler,
        *,
        replay: ReplayPosition | int = ReplayPosition.LATEST,
    ) -> str:
        subscription_id = self._allocate_subscription_id()
        subscription = Subscription(
            id=subscription_id,
            event_type=event_type,
            handler=handler,
        )
        self._subscriptions[subscription_id] = subscription
        self._by_type[event_type].add(subscription_id)

        if replay != ReplayPosition.LATEST:
            after_sequence = 0 if replay == ReplayPosition.BEGINNING else int(replay)
            asyncio.create_task(self._replay_to(subscription, after_sequence))

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        subscription = self._subscriptions.pop(subscription_id)
        self._by_type[subscription.event_type].discard(subscription_id)

    def _allocate_subscription_id(self) -> str:
        subscription_id = f"sub_{self._next_subscription}"
        self._next_subscription += 1
        return subscription_id

    def _subscriptions_for(self, event_type: EventType) -> tuple[Subscription, ...]:
        ids = self._by_type[event_type] | self._by_type[None]
        return tuple(
            self._subscriptions[subscription_id]
            for subscription_id in sorted(ids)
            if subscription_id in self._subscriptions
        )

    async def _replay_to(self, subscription: Subscription, after_sequence: int) -> None:
        stored_events = await self._store.replay(
            after_sequence=after_sequence,
            event_type=subscription.event_type,
        )
        for stored in stored_events:
            if subscription.id not in self._subscriptions:
                return
            await self._deliver(stored.event, (subscription,))

    async def _deliver(self, event: Event, subscriptions: tuple[Subscription, ...]) -> None:
        for subscription in subscriptions:
            try:
                await subscription.handler(event)
            except Exception as exc:
                self._dead_letters.append(
                    DeadLetter(
                        event=event,
                        handler_name=getattr(
                            subscription.handler,
                            "__name__",
                            subscription.id,
                        ),
                        error=str(exc),
                    )
                )
