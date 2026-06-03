"""Compatibility exports for the B5 event bus module."""

from anubis.distributed.event_bus import EventBus, EventHandler, InMemoryEventBus

__all__ = ["EventBus", "EventHandler", "InMemoryEventBus"]
