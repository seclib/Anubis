"""Concrete service container used by API and workers."""

from __future__ import annotations

from crawler.service import CrawlerService, get_crawler_service
from intelligence.service import IntelligenceService, get_intelligence_service
from knowledge.service import KnowledgeService, get_knowledge_service
from rag.service import RAGService, get_rag_service
from services.cache_manager import CacheManager, get_cache_manager
from storage.redis import RedisStore


class ServiceContainer:
    def __init__(self) -> None:
        self.rag: RAGService = get_rag_service()
        self.crawler: CrawlerService = get_crawler_service()
        self.knowledge: KnowledgeService = get_knowledge_service()
        self.intelligence: IntelligenceService = get_intelligence_service()
        self.redis: RedisStore = RedisStore()
        self.cache: CacheManager = get_cache_manager()

    def health(self) -> dict[str, object]:
        return {
            "rag": self.rag.health(),
            "crawler": {"ok": True},
            "knowledge": self.knowledge.vault_health(),
            "intelligence": {"ok": True},
            "redis": self.redis.health(),
            "cache": self.cache.health(),
        }


_CONTAINER: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = ServiceContainer()
    return _CONTAINER


__all__ = ["ServiceContainer", "get_container"]
