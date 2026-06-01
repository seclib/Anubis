"""Synchronous job helpers used by local workers and tests."""

from __future__ import annotations

import asyncio
from typing import Any

from crawler.service import get_crawler_service
from knowledge.service import get_knowledge_service
from retrieval.service import get_retrieval_service
from workers.maintenance_jobs import get_background_loop


def crawl_once(query: str, seeds: list[str] | None = None, max_pages: int = 10) -> dict[str, Any]:
    return asyncio.run(
        get_crawler_service().crawl(
            query=query,
            seeds=seeds or [],
            max_pages=max_pages,
            max_depth=1,
            ingest=True,
        )
    )


def maintain_vault() -> dict[str, Any]:
    return get_knowledge_service().maintain(apply=True)


def reindex_vault() -> dict[str, Any]:
    return get_retrieval_service().obsidian.ingest(force=True, index_qdrant=True)


def background_once() -> dict[str, Any]:
    return asyncio.run(get_background_loop().run_once())


__all__ = ["background_once", "crawl_once", "maintain_vault", "reindex_vault"]
