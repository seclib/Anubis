"""Persistence adapters for the ANUBIS distributed state machine."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from threading import RLock
from typing import Any, Protocol


class StatePersistence(Protocol):
    def save(self, task_id: str, payload: Mapping[str, Any]) -> None: ...
    def load(self, task_id: str) -> dict[str, Any] | None: ...
    def load_all(self) -> tuple[dict[str, Any], ...]: ...


class InMemoryStatePersistence:
    """Deterministic persistence adapter for tests and local workers."""

    def __init__(self, initial: Iterable[Mapping[str, Any]] | None = None) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
        for record in initial or ():
            task_id = str(record["task_id"])
            self._records[task_id] = dict(record)

    def save(self, task_id: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            self._records[task_id] = dict(payload)

    def load(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._records.get(task_id)
            return dict(payload) if payload is not None else None

    def load_all(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(record) for record in self._records.values())


class RedisStatePersistence:
    """Redis-backed task state persistence.

    The adapter intentionally stores plain JSON values under predictable keys so
    state can be recovered after process crashes by scanning the prefix.
    """

    def __init__(
        self,
        *,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "anubis:state:",
        client: Any | None = None,
    ) -> None:
        self.key_prefix = key_prefix
        if client is not None:
            self.client = client
            return
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("redis package is required for RedisStatePersistence") from exc
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)

    def save(self, task_id: str, payload: Mapping[str, Any]) -> None:
        self.client.set(self._key(task_id), json.dumps(dict(payload), sort_keys=True, default=str))

    def load(self, task_id: str) -> dict[str, Any] | None:
        raw = self.client.get(self._key(task_id))
        if raw is None:
            return None
        return dict(json.loads(raw))

    def load_all(self) -> tuple[dict[str, Any], ...]:
        records: list[dict[str, Any]] = []
        pattern = f"{self.key_prefix}*"
        for key in self.client.scan_iter(match=pattern):
            raw = self.client.get(key)
            if raw is not None:
                records.append(dict(json.loads(raw)))
        records.sort(key=lambda item: str(item.get("task_id", "")))
        return tuple(records)

    def _key(self, task_id: str) -> str:
        return f"{self.key_prefix}{task_id}"


__all__ = [
    "InMemoryStatePersistence",
    "RedisStatePersistence",
    "StatePersistence",
]
