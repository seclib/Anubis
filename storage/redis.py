"""Redis adapter used by caches, rate limits, and job state."""

from __future__ import annotations

import json
from typing import Any

from config import REDIS_CACHE_ENABLED, REDIS_CACHE_URL

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


class RedisStore:
    def __init__(self, url: str = REDIS_CACHE_URL, enabled: bool = REDIS_CACHE_ENABLED) -> None:
        self.url = url
        self.enabled = enabled
        self._client: Any | None = None

    @property
    def client(self) -> Any | None:
        if not self.enabled or redis is None:
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        return self._client

    def health(self) -> dict[str, Any]:
        client = self.client
        if client is None:
            return {"ok": False, "enabled": self.enabled, "error": "redis package disabled or unavailable"}
        try:
            client.ping()
            return {"ok": True, "url": self.url}
        except Exception as exc:
            return {"ok": False, "url": self.url, "error": str(exc)}

    def get_json(self, key: str) -> Any | None:
        client = self.client
        if client is None:
            return None
        try:
            value = client.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        client = self.client
        if client is None:
            return False
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            client.set(key, payload, ex=ttl_seconds)
            return True
        except Exception:
            return False


__all__ = ["RedisStore"]

