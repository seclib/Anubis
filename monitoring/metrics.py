"""Minimal local metrics snapshot."""

from __future__ import annotations

from typing import Any

from knowledge.service import get_knowledge_service
from retrieval.service import get_retrieval_service
from services.cache_manager import get_cache_manager
from storage.redis import RedisStore
from workers.maintenance_jobs import get_background_loop


def metrics_snapshot() -> dict[str, Any]:
    retrieval_health = get_retrieval_service().health()
    knowledge_health = get_knowledge_service().vault_health()
    redis_health = RedisStore().health()
    cache_health = get_cache_manager().health()
    return {
        "retrieval": retrieval_health,
        "knowledge": knowledge_health,
        "redis": redis_health,
        "cache": cache_health,
        "background": get_background_loop().last_result,
    }


__all__ = ["metrics_snapshot"]
