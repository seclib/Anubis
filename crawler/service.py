"""Autonomous local OSINT crawl and ingestion service."""

from __future__ import annotations

from typing import Any

from crawler.workers import AsyncCrawlerWorkerPool


DEFAULT_SEEDS = [
    "https://attack.mitre.org/",
    "https://www.cisa.gov/news-events/cybersecurity-advisories",
    "https://github.com/topics/security-tools",
]


class CrawlerService:
    def __init__(self) -> None:
        self.default_workers = 8

    async def crawl(
        self,
        *,
        query: str,
        seeds: list[str] | None = None,
        max_pages: int = 10,
        max_depth: int = 1,
        ingest: bool = True,
        workers: int | None = None,
    ) -> dict[str, Any]:
        pool = AsyncCrawlerWorkerPool(
            query=query,
            max_pages=max_pages,
            max_depth=max_depth,
            ingest=ingest,
            workers=workers or self.default_workers,
        )
        return await pool.run(seeds or DEFAULT_SEEDS)


_SERVICE: CrawlerService | None = None


def get_crawler_service() -> CrawlerService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CrawlerService()
    return _SERVICE


__all__ = ["CrawlerService", "get_crawler_service"]
