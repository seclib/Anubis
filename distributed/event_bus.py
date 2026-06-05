"""Async pub/sub event bus for ANUBIS distributed agents."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Future, ThreadPoolExecutor
from inspect import isawaitable
from threading import RLock
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent


EventHandlerResult = None | Awaitable[None]
EventHandler = Callable[[OrchestrationEvent], EventHandlerResult]


class EventBus:
    """Non-blocking in-process pub/sub bus.

    This is communication infrastructure only. It stores emitted events and
    dispatches handlers concurrently without encoding orchestration decisions.
    """

    def __init__(self, *, max_workers: int = 8) -> None:
        self._events: list[OrchestrationEvent] = []
        self._subscribers: dict[EventType | None, list[EventHandler]] = {}
        self._pending: list[asyncio.Task[Any] | Future[Any]] = []
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="anubis-event")
        self._lock = RLock()

    def publish(self, event: OrchestrationEvent) -> OrchestrationEvent:
        with self._lock:
            self._events.append(event)
            handlers = (
                *self._subscribers.get(event.event_type, ()),
                *self._subscribers.get(None, ()),
            )

        for handler in handlers:
            pending = self._dispatch(handler, event)
            if pending is not None:
                with self._lock:
                    self._pending.append(pending)
        return event

    def emit(self, event: OrchestrationEvent) -> OrchestrationEvent:
        """Compatibility alias for earlier B1 orchestration code."""
        return self.publish(event)

    async def publish_async(self, event: OrchestrationEvent) -> OrchestrationEvent:
        return self.publish(event)

    def subscribe(
        self,
        event_type: EventType | str | EventHandler | None,
        handler: EventHandler | EventType | str | None = None,
    ) -> None:
        """Subscribe a handler to an event type.

        Passing ``None`` subscribes to every event. The method intentionally
        accepts event type strings because external workers may deserialize
        event names from a broker.
        """
        if callable(event_type) and (handler is None or isinstance(handler, (EventType, str))):
            actual_handler = event_type
            normalized = self._normalize_event_type(handler)
        else:
            actual_handler = handler
            normalized = self._normalize_event_type(event_type if not callable(event_type) else None)

        if actual_handler is None or not callable(actual_handler):
            raise ValueError("handler is required")
        with self._lock:
            self._subscribers.setdefault(normalized, []).append(actual_handler)

    async def drain(self) -> None:
        """Wait for all currently scheduled handlers to finish."""
        while True:
            with self._lock:
                pending = tuple(self._pending)
                self._pending.clear()
            if not pending:
                return
            await asyncio.gather(
                *(item if isinstance(item, asyncio.Future) else asyncio.wrap_future(item) for item in pending),
                return_exceptions=True,
            )

    def events(self) -> tuple[OrchestrationEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _dispatch(
        self,
        handler: EventHandler,
        event: OrchestrationEvent,
    ) -> asyncio.Task[Any] | Future[Any] | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return self._executor.submit(self._run_handler_without_loop, handler, event)

        return loop.create_task(self._run_handler(handler, event))

    async def _run_handler(self, handler: EventHandler, event: OrchestrationEvent) -> None:
        result = handler(event)
        if isawaitable(result):
            await result

    def _run_handler_without_loop(self, handler: EventHandler, event: OrchestrationEvent) -> None:
        result = handler(event)
        if isawaitable(result):
            asyncio.run(result)

    def _normalize_event_type(self, event_type: EventType | str | None) -> EventType | None:
        if event_type is None:
            return None
        if isinstance(event_type, EventType):
            return event_type
        return EventType(event_type)


class InMemoryEventBus(EventBus):
    """Backward-compatible name for the default in-process bus."""


__all__ = ["EventBus", "EventHandler", "InMemoryEventBus"]
