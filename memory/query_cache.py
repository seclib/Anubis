"""Redis-first query/result cache for fast knowledge reuse."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    QUERY_CACHE_ENABLED,
    QUERY_CACHE_FILE,
    REDIS_CACHE_ENABLED,
    REDIS_CACHE_NAMESPACE,
    REDIS_CACHE_TTL_SECONDS,
    REDIS_CACHE_URL,
)
from core.workspace import relative_to_workspace, resolve_workspace_path, workspace_root
from memory import vector

try:
    import redis
except ImportError:  # pragma: no cover - optional runtime dependency
    redis = None

MAX_CACHE_ENTRIES = 500
MAX_RESULT_CHARS = 12000
REDIS_SOCKET_TIMEOUT = 0.2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path() -> Path:
    path = QUERY_CACHE_FILE
    if not path.is_absolute():
        path = workspace_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return resolve_workspace_path(path, must_exist=False)


def _default_cache() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "entries": [],
    }


def _redis_client() -> Any | None:
    if not REDIS_CACHE_ENABLED or redis is None:
        return None
    try:
        client = redis.Redis.from_url(
            REDIS_CACHE_URL,
            decode_responses=True,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
        )
        client.ping()
        return client
    except Exception:
        return None


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_À-ÿ-]{3,}", value.lower())}


def _similarity(left: str, right: str) -> float:
    if left.strip().lower() == right.strip().lower() and left.strip():
        return 1.0
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _semantic_similarity(query: str, entry: dict[str, Any]) -> float:
    embedding = entry.get("query_embedding")
    if not isinstance(embedding, list):
        return 0.0
    try:
        query_embedding = vector._hash_embedding(query)
        return max(0.0, vector._cosine(query_embedding, [float(value) for value in embedding]))
    except Exception:
        return 0.0


def _cache_key(query: str) -> str:
    normalized = query.strip().lower()
    import hashlib

    digest = hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()
    return f"{REDIS_CACHE_NAMESPACE}:entry:{digest}"


def _index_key() -> str:
    return f"{REDIS_CACHE_NAMESPACE}:index"


def _entry_payload(
    query: str,
    result: Any,
    context: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "query": query.strip(),
        "query_embedding": vector._hash_embedding(query),
        "result": str(result)[:MAX_RESULT_CHARS],
        "context": context[:4000],
        "metadata": metadata or {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _format_matches(
    query: str,
    entries: list[dict[str, Any]],
    top_k: int,
    backend: str,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for entry in entries:
        cached_query = str(entry.get("query") or "")
        lexical_confidence = _similarity(query, cached_query)
        semantic_confidence = _semantic_similarity(query, entry)
        confidence = max(lexical_confidence, semantic_confidence)
        if confidence <= 0:
            continue
        matches.append(
            {
                "confidence": round(confidence, 6),
                "semantic_confidence": round(semantic_confidence, 6),
                "lexical_confidence": round(lexical_confidence, 6),
                "query": cached_query,
                "result": str(entry.get("result") or "")[:MAX_RESULT_CHARS],
                "context": str(entry.get("context") or "")[:4000],
                "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
                "updated_at": entry.get("updated_at") or entry.get("created_at"),
            }
        )
    matches.sort(key=lambda item: (float(item["confidence"]), str(item.get("updated_at") or "")), reverse=True)
    best = matches[0] if matches else None
    return {
        "enabled": True,
        "backend": backend,
        "hit": bool(best),
        "confidence": float(best["confidence"]) if best else 0.0,
        "best": best,
        "matches": matches[: max(1, int(top_k))],
        "partial_match": bool(best) and float(best["confidence"]) <= 0.85,
        "needs_enrichment": bool(best) and float(best["confidence"]) <= 0.85,
        "next_layer": "qdrant" if not best or float(best["confidence"]) <= 0.85 else "final",
    }


def _lookup_redis_cache(query: str, top_k: int) -> dict[str, Any] | None:
    client = _redis_client()
    if client is None:
        return None
    key = _cache_key(query)
    try:
        exact_payload = client.get(key)
        if exact_payload:
            entry = json.loads(exact_payload)
            if isinstance(entry, dict):
                result = _format_matches(query, [entry], top_k, "redis")
                result["redis_hit_type"] = "exact"
                return result

        entries: list[dict[str, Any]] = []
        for cached_key in client.zrevrange(_index_key(), 0, MAX_CACHE_ENTRIES - 1):
            payload = client.get(cached_key)
            if not payload:
                continue
            entry = json.loads(payload)
            if isinstance(entry, dict):
                entries.append(entry)
        result = _format_matches(query, entries, top_k, "redis")
        result["redis_hit_type"] = "similar" if result["hit"] else "miss"
        return result
    except Exception:
        return None


def _store_redis_cache(entry: dict[str, Any]) -> dict[str, Any] | None:
    client = _redis_client()
    if client is None:
        return None
    try:
        key = _cache_key(str(entry.get("query") or ""))
        payload = json.dumps(entry, ensure_ascii=False, default=str)
        ttl = max(60, int(REDIS_CACHE_TTL_SECONDS))
        client.set(key, payload, ex=ttl)
        client.zadd(_index_key(), {key: datetime.now(timezone.utc).timestamp()})
        client.expire(_index_key(), ttl)
        return {
            "enabled": True,
            "backend": "redis",
            "stored": True,
            "entry": entry,
            "key": key,
            "ttl_seconds": ttl,
        }
    except Exception:
        return None


def load_query_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.exists():
        return _default_cache()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_cache()
    if not isinstance(data, dict):
        return _default_cache()
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    data.setdefault("version", 1)
    data.setdefault("created_at", _now_iso())
    data["updated_at"] = data.get("updated_at") or _now_iso()
    return data


def save_query_cache(cache: dict[str, Any]) -> None:
    cache["updated_at"] = _now_iso()
    entries = [entry for entry in cache.get("entries", []) if isinstance(entry, dict)]
    cache["entries"] = entries[-MAX_CACHE_ENTRIES:]
    path = _cache_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def lookup_query_cache(query: str, top_k: int = 3) -> dict[str, Any]:
    """Return cached answers using Redis first, then local file fallback."""
    if not QUERY_CACHE_ENABLED or not query.strip():
        return {"enabled": QUERY_CACHE_ENABLED, "backend": "disabled", "hit": False, "confidence": 0.0, "matches": []}

    redis_result = _lookup_redis_cache(query, top_k)
    if redis_result is not None:
        return redis_result

    entries = []
    for entry in load_query_cache().get("entries", []):
        if not isinstance(entry, dict):
            continue
        entries.append(entry)
    result = _format_matches(query, entries, top_k, "file")
    result["store"] = relative_to_workspace(_cache_path())
    result["redis_available"] = False
    return result


def store_query_cache(
    query: str,
    result: Any,
    context: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store or replace a cached answer for a stable query."""
    if not QUERY_CACHE_ENABLED or not query.strip():
        return {"enabled": QUERY_CACHE_ENABLED, "stored": False}

    normalized_query = query.strip()
    entry = _entry_payload(
        query=normalized_query,
        result=result,
        context=context,
        metadata=metadata,
    )
    redis_result = _store_redis_cache(entry)
    if redis_result is not None:
        return redis_result

    cache = load_query_cache()
    entries = [cached_entry for cached_entry in cache.get("entries", []) if isinstance(cached_entry, dict)]
    entries = [
        cached_entry
        for cached_entry in entries
        if str(cached_entry.get("query") or "").strip().lower() != normalized_query.lower()
    ]
    entries.append(entry)
    cache["entries"] = entries
    save_query_cache(cache)
    return {
        "enabled": True,
        "backend": "file",
        "stored": True,
        "entry": entry,
        "store": relative_to_workspace(_cache_path()),
        "redis_available": False,
    }


def invalidate_query_cache(query: str | None = None) -> dict[str, Any]:
    """Invalidate local fallback query cache entries."""
    cache = load_query_cache()
    entries = [entry for entry in cache.get("entries", []) if isinstance(entry, dict)]
    if query is None or not str(query).strip():
        deleted = len(entries)
        cache["entries"] = []
    else:
        normalized = str(query).strip().lower()
        kept = [
            entry
            for entry in entries
            if str(entry.get("query") or "").strip().lower() != normalized
        ]
        deleted = len(entries) - len(kept)
        cache["entries"] = kept
    save_query_cache(cache)
    return {
        "enabled": QUERY_CACHE_ENABLED,
        "backend": "file",
        "deleted": deleted,
        "store": relative_to_workspace(_cache_path()),
    }


__all__ = [
    "invalidate_query_cache",
    "load_query_cache",
    "lookup_query_cache",
    "save_query_cache",
    "store_query_cache",
]
