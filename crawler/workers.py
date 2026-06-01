"""Async crawler worker pool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from crawler.deduplication import DedupeLedger, content_hash, normalize_url
from crawler.extraction import extract_content, render_obsidian_note
from crawler.fetcher import fetch_url
from crawler.noise import is_noise_content, should_fetch_url
from crawler.parser import parse_html
from crawler.scoring import quality_score, source_trust, url_priority
from rag.service import get_rag_service


@dataclass(order=True)
class CrawlTask:
    priority: float
    url: str = field(compare=False)
    depth: int = field(compare=False, default=0)
    discovered_from: str = field(compare=False, default="")


class AsyncCrawlerWorkerPool:
    def __init__(
        self,
        *,
        query: str,
        max_pages: int,
        max_depth: int,
        ingest: bool,
        workers: int = 8,
    ) -> None:
        self.query = query
        self.max_pages = max(1, min(int(max_pages), 500))
        self.max_depth = max(0, min(int(max_depth), 5))
        self.ingest = ingest
        self.workers = max(1, min(int(workers), 64))
        self.queue: asyncio.PriorityQueue[CrawlTask] = asyncio.PriorityQueue()
        self.ledger = DedupeLedger()
        self.scheduled: set[str] = set()
        self.results: list[dict[str, Any]] = []
        self.ingested: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def run(self, seeds: list[str]) -> dict[str, Any]:
        for seed in seeds:
            self.schedule(seed, depth=0, discovered_from="")

        timeout = httpx.Timeout(connect=5, read=20, write=5, pool=5)
        limits = httpx.Limits(max_connections=max(8, self.workers * 4), max_keepalive_connections=max(4, self.workers * 2))
        async with httpx.AsyncClient(timeout=timeout, limits=limits, headers={"User-Agent": "Anubis-OSINT/3.1"}) as client:
            tasks = [asyncio.create_task(self._worker(client, worker_id)) for worker_id in range(self.workers)]
            await self.queue.join()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        reindex = None
        if self.ingest and self.ingested:
            reindex = await asyncio.to_thread(
                get_rag_service().ingest_obsidian,
                limit=None,
                force=False,
                index_qdrant=True,
            )

        return {
            "query": self.query,
            "pages_processed": len(self.results),
            "notes_ingested": len(self.ingested),
            "errors": self.errors[:100],
            "results": self.results,
            "ingested": self.ingested,
            "reindex": reindex,
        }

    def schedule(self, url: str, *, depth: int, discovered_from: str) -> bool:
        if depth > self.max_depth:
            return False
        normalized = normalize_url(url)
        if normalized in self.scheduled or not should_fetch_url(normalized):
            return False
        self.scheduled.add(normalized)
        priority = -url_priority(normalized, self.query)
        self.queue.put_nowait(CrawlTask(priority=priority, url=normalized, depth=depth, discovered_from=discovered_from))
        return True

    async def _worker(self, client: httpx.AsyncClient, worker_id: int) -> None:
        while True:
            task = await self.queue.get()
            try:
                async with self._lock:
                    if len(self.results) >= self.max_pages:
                        continue
                if self.ledger.seen_url(task.url):
                    continue
                record = await self._process(client, task, worker_id)
                if record:
                    async with self._lock:
                        if len(self.results) < self.max_pages:
                            self.results.append(record)
            finally:
                self.queue.task_done()

    async def _process(self, client: httpx.AsyncClient, task: CrawlTask, worker_id: int) -> dict[str, Any] | None:
        fetched = await fetch_url(client, task.url)
        if fetched.get("error"):
            error = {"url": task.url, "error": fetched.get("error"), "worker_id": worker_id}
            self.errors.append(error)
            return error

        url = str(fetched.get("url") or task.url)
        parsed = parse_html(url, str(fetched.get("text") or ""))
        extracted = extract_content(parsed, url=url, query=self.query)
        text = str(extracted.get("text") or "")
        if is_noise_content(text):
            return {
                "url": url,
                "status_code": fetched.get("status_code"),
                "noise": True,
                "metadata": {"depth": task.depth, "worker_id": worker_id},
            }

        digest = content_hash(text)
        score = quality_score(text, url)
        record = {
            "url": url,
            "status_code": fetched.get("status_code"),
            "title": extracted.get("title"),
            "text": text[:12000],
            "links": extracted.get("links", []),
            "entities": extracted.get("entities", []),
            "quality_score": score,
            "trust_score": source_trust(url),
            "content_hash": digest,
            "metadata": {"depth": task.depth, "discovered_from": task.discovered_from, "worker_id": worker_id},
        }

        if text and not self.ledger.seen_content(text) and self.ingest and score >= 0.25:
            note = render_obsidian_note(
                extracted,
                {
                    "quality_score": score,
                    "trust_score": source_trust(url),
                    "status_code": fetched.get("status_code"),
                    "content_hash": digest,
                },
            )
            ingest_result = await asyncio.to_thread(
                get_rag_service().ingest,
                title=str(record["title"]),
                content=note,
                source_url=url,
                folder="OSINT",
                metadata={
                    "quality_score": score,
                    "trust_score": source_trust(url),
                    "content_hash": digest,
                    "domain": "osint",
                    "source_type": "osint",
                },
            )
            self.ingested.append(ingest_result)

        if task.depth < self.max_depth:
            for link in list(extracted.get("links", []))[:80]:
                self.schedule(str(link), depth=task.depth + 1, discovered_from=url)

        return record


__all__ = ["AsyncCrawlerWorkerPool", "CrawlTask"]
