"""Redis-backed semantic cache manager for retrieval."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

from config import (
    EMBEDDING_MODEL,
    QUERY_CACHE_ENABLED,
    QUERY_CACHE_HIT_THRESHOLD,
    REDIS_CACHE_NAMESPACE,
    REDIS_CACHE_TTL_SECONDS,
)
from memory import query_cache, vector
from storage.redis import RedisStore

EmbeddingFn = Callable[[str], list[float]]

MAX_SEMANTIC_CACHE_SCAN = 500
SEMANTIC_REUSE_THRESHOLD = max(0.90, float(QUERY_CACHE_HIT_THRESHOLD))
SEMANTIC_RERANK_THRESHOLD = 0.88


class CacheManager:
    """Cache query results and embeddings with Redis-first semantics."""

    def __init__(self, redis_store: RedisStore | None = None) -> None:
        self.redis = redis_store or RedisStore()

    def health(self) -> dict[str, Any]:
        redis_health = self.redis.health()
        return {
            "enabled": QUERY_CACHE_ENABLED,
            "redis": redis_health,
            "namespace": REDIS_CACHE_NAMESPACE,
            "semantic_reuse_threshold": SEMANTIC_REUSE_THRESHOLD,
        }

    def get_embedding(
        self,
        text: str,
        *,
        model: str = EMBEDDING_MODEL,
        embedder: EmbeddingFn | None = None,
    ) -> dict[str, Any]:
        clean_text = str(text or "")
        key = self._embedding_key(clean_text, model)
        cached = self.redis.get_json(key)
        if isinstance(cached, dict) and isinstance(cached.get("embedding"), list):
            return {
                "embedding": [float(value) for value in cached["embedding"]],
                "cache": {"hit": True, "backend": "redis", "key": key},
            }

        embedding = (embedder or vector._hash_embedding)(clean_text)
        stored = self.redis.set_json(
            key,
            {
                "text_hash": self._hash(clean_text),
                "model": model,
                "embedding": embedding,
                "created_at": self._now_iso(),
            },
            ttl_seconds=max(60, int(REDIS_CACHE_TTL_SECONDS)),
        )
        return {
            "embedding": embedding,
            "cache": {"hit": False, "backend": "redis" if stored else "local", "key": key, "stored": stored},
        }

    def lookup_query(
        self,
        query: str,
        *,
        query_embedding: list[float] | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int = 1,
    ) -> dict[str, Any]:
        if not QUERY_CACHE_ENABLED or not str(query or "").strip():
            return {"enabled": QUERY_CACHE_ENABLED, "hit": False, "backend": "disabled"}

        filters_hash = self._filters_hash(filters or {})
        exact_key = self._query_key(query, filters_hash)
        cached = self.redis.get_json(exact_key)
        if isinstance(cached, dict):
            return {
                "enabled": True,
                "hit": True,
                "backend": "redis",
                "hit_type": "exact",
                "confidence": 1.0,
                "entry": cached,
                "matches": [cached],
            }

        semantic = self._lookup_semantic_redis(
            query=query,
            query_embedding=query_embedding or vector._hash_embedding(query),
            filters_hash=filters_hash,
            top_k=top_k,
        )
        if semantic.get("hit"):
            return semantic

        fallback = query_cache.lookup_query_cache(query, top_k=top_k)
        fallback["filters_hash"] = filters_hash
        return fallback

    def store_query(
        self,
        query: str,
        *,
        result: Any,
        context: str = "",
        metadata: dict[str, Any] | None = None,
        query_embedding: list[float] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not QUERY_CACHE_ENABLED or not str(query or "").strip():
            return {"enabled": QUERY_CACHE_ENABLED, "stored": False}

        filters_hash = self._filters_hash(filters or {})
        embedding = query_embedding or vector._hash_embedding(query)
        entry = {
            "query": query.strip(),
            "query_hash": self._hash(query.strip().lower()),
            "filters_hash": filters_hash,
            "query_embedding": embedding,
            "result": result,
            "context": str(context or "")[:12000],
            "metadata": metadata or {},
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
        }
        ttl = max(60, int(REDIS_CACHE_TTL_SECONDS))
        exact_key = self._query_key(query, filters_hash)
        stored = self.redis.set_json(exact_key, entry, ttl_seconds=ttl)
        semantic_stored = self._store_semantic_index(exact_key, entry, ttl)
        fallback = query_cache.store_query_cache(
            query,
            result,
            context=context,
            metadata={**(metadata or {}), "filters_hash": filters_hash},
        )
        return {
            "enabled": True,
            "stored": bool(stored or fallback.get("stored")),
            "backend": "redis" if stored else fallback.get("backend", "file"),
            "key": exact_key,
            "semantic_indexed": semantic_stored,
            "fallback": fallback,
        }

    def invalidate(
        self,
        *,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        include_embeddings: bool = False,
    ) -> dict[str, Any]:
        client = self.redis.client
        local_result = query_cache.invalidate_query_cache(query)
        if client is None:
            return {
                "ok": bool(local_result.get("deleted", 0) >= 0),
                "backend": "file",
                "redis": {"ok": False, "deleted": 0, "error": "redis unavailable"},
                "local": local_result,
            }
        patterns: list[str] = []
        if query:
            filters_hash = self._filters_hash(filters or {})
            patterns.append(self._query_key(query, filters_hash))
        else:
            patterns.extend(
                [
                    f"{REDIS_CACHE_NAMESPACE}:query:*",
                    f"{REDIS_CACHE_NAMESPACE}:semantic_index:*",
                ]
            )
        if include_embeddings:
            patterns.append(f"{REDIS_CACHE_NAMESPACE}:embedding:*")
        deleted = 0
        try:
            for pattern in patterns:
                for key in client.scan_iter(match=pattern, count=200):
                    deleted += int(client.delete(key) or 0)
            return {
                "ok": True,
                "backend": "redis+file",
                "deleted": deleted + int(local_result.get("deleted") or 0),
                "redis": {"ok": True, "deleted": deleted, "patterns": patterns},
                "local": local_result,
            }
        except Exception as exc:
            return {
                "ok": bool(local_result.get("deleted", 0) >= 0),
                "backend": "file",
                "deleted": int(local_result.get("deleted") or 0),
                "redis": {"ok": False, "deleted": deleted, "error": str(exc)},
                "local": local_result,
            }

    def _lookup_semantic_redis(
        self,
        *,
        query: str,
        query_embedding: list[float],
        filters_hash: str,
        top_k: int,
    ) -> dict[str, Any]:
        client = self.redis.client
        if client is None:
            return {"enabled": True, "hit": False, "backend": "redis", "redis_available": False}
        try:
            index_key = self._semantic_index_key(filters_hash)
            cached_keys = client.zrevrange(index_key, 0, MAX_SEMANTIC_CACHE_SCAN - 1)
        except Exception:
            return {"enabled": True, "hit": False, "backend": "redis", "redis_available": False}

        matches: list[dict[str, Any]] = []
        for cached_key in cached_keys:
            entry = self.redis.get_json(str(cached_key))
            if not isinstance(entry, dict):
                continue
            embedding = entry.get("query_embedding")
            if not isinstance(embedding, list):
                continue
            confidence = max(
                self._lexical_similarity(query, str(entry.get("query") or "")),
                max(0.0, vector._cosine(query_embedding, [float(value) for value in embedding])),
            )
            if confidence < SEMANTIC_RERANK_THRESHOLD:
                continue
            matches.append(
                {
                    **entry,
                    "confidence": round(confidence, 6),
                    "semantic_confidence": round(max(0.0, vector._cosine(query_embedding, [float(value) for value in embedding])), 6),
                }
            )
        matches.sort(key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
        best = matches[0] if matches else None
        return {
            "enabled": True,
            "hit": bool(best and float(best.get("confidence") or 0.0) >= SEMANTIC_REUSE_THRESHOLD),
            "partial_hit": bool(best and float(best.get("confidence") or 0.0) >= SEMANTIC_RERANK_THRESHOLD),
            "backend": "redis",
            "hit_type": "semantic" if best else "miss",
            "confidence": float(best.get("confidence") or 0.0) if best else 0.0,
            "entry": best,
            "matches": matches[: max(1, int(top_k))],
        }

    def _store_semantic_index(self, exact_key: str, entry: dict[str, Any], ttl: int) -> bool:
        client = self.redis.client
        if client is None:
            return False
        try:
            index_key = self._semantic_index_key(str(entry.get("filters_hash") or "none"))
            client.zadd(index_key, {exact_key: datetime.now(timezone.utc).timestamp()})
            client.expire(index_key, ttl)
            return True
        except Exception:
            return False

    def _embedding_key(self, text: str, model: str) -> str:
        return f"{REDIS_CACHE_NAMESPACE}:embedding:{model}:{self._hash(text)}"

    def _query_key(self, query: str, filters_hash: str) -> str:
        return f"{REDIS_CACHE_NAMESPACE}:query:{filters_hash}:{self._hash(query.strip().lower())}"

    def _semantic_index_key(self, filters_hash: str) -> str:
        return f"{REDIS_CACHE_NAMESPACE}:semantic_index:{filters_hash}"

    def _filters_hash(self, filters: dict[str, Any]) -> str:
        payload = json.dumps(filters or {}, sort_keys=True, ensure_ascii=False, default=str)
        return self._hash(payload)[:16]

    def _hash(self, value: str) -> str:
        return hashlib.sha256(str(value or "").encode("utf-8", errors="ignore")).hexdigest()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _lexical_similarity(self, left: str, right: str) -> float:
        left_tokens = set(str(left).lower().split())
        right_tokens = set(str(right).lower().split())
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


_CACHE_MANAGER: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    global _CACHE_MANAGER
    if _CACHE_MANAGER is None:
        _CACHE_MANAGER = CacheManager()
    return _CACHE_MANAGER


__all__ = ["CacheManager", "get_cache_manager"]
