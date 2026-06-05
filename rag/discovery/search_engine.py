from __future__ import annotations

import json
import math
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

from rag.discovery.embedding import DiscoveryEmbeddingPipeline
from rag.discovery.schema import DiscoveryEntry, DiscoverySearchResult, read_jsonl
from rag.shared.qdrant_client import QdrantVectorStore


class _TTLCache:
    def __init__(self, max_size: int = 128, ttl_seconds: float = 300.0) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        created, value = item
        if time.monotonic() - created > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)


class DiscoverySearchEngine:
    domain = "discovery"
    _cache = _TTLCache()

    def __init__(
        self,
        index_path: str | Path = "state/discovery_index.jsonl",
        embedding: DiscoveryEmbeddingPipeline | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.index_path = Path(index_path)
        self.embedding = embedding or DiscoveryEmbeddingPipeline()
        self.vector_store = vector_store or QdrantVectorStore(self.embedding.embedder)
        self.entries = self.load_entries()

    def load_entries(self) -> list[DiscoveryEntry]:
        return [DiscoveryEntry.from_dict(row) for row in read_jsonl(self.index_path)]

    def reload(self) -> None:
        self.entries = self.load_entries()
        self._cache = _TTLCache()

    def search(
        self,
        query: str,
        search_engine: str | None = None,
        category: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        limit: int = 10,
    ) -> list[DiscoverySearchResult]:
        normalized_tags = tuple(sorted(str(tag) for tag in (tags or ()) if str(tag).strip()))
        cache_key = json.dumps([query, search_engine, category, normalized_tags, limit], sort_keys=True)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        filters = self._filters(search_engine, category, normalized_tags)
        candidates = self._filter_entries(filters)
        semantic = self._semantic_scores(query, filters, max(limit * 4, 20))
        semantic_by_doc = {str(item.get("doc_id") or item.get("chunk_id") or ""): float(item.get("score") or 0.0) for item in semantic}
        terms = self._terms(query)
        results = []
        for entry in candidates:
            keyword_score, matched = self._keyword_score(entry, terms)
            semantic_score = max(
                semantic_by_doc.get(entry.doc_id, 0.0),
                max((score for key, score in semantic_by_doc.items() if key.startswith(entry.doc_id)), default=0.0),
            )
            score = round(0.60 * keyword_score + 0.40 * semantic_score, 6)
            if score > 0 or not terms:
                results.append(DiscoverySearchResult(entry, score, keyword_score, semantic_score, tuple(matched)))
        ranked = sorted(results, key=lambda result: result.score, reverse=True)[:limit]
        self._cache.set(cache_key, ranked)
        return ranked

    def cli_summary(self, results: list[DiscoverySearchResult]) -> str:
        if not results:
            return "no discovery queries found"
        return "\n".join(result.cli_summary() for result in results)

    def structured(self, results: list[DiscoverySearchResult]) -> list[dict[str, Any]]:
        return [result.to_dict() for result in results]

    def _semantic_scores(self, query: str, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        try:
            return self.vector_store.search(self.domain, query, top_k=limit, filters=filters)
        except Exception:
            return []

    def _filters(self, search_engine: str | None, category: str | None, tags: tuple[str, ...]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if search_engine:
            filters["search_engine"] = [search_engine]
        if category:
            filters["category"] = [category]
        if tags:
            filters["tags"] = list(tags)
        return filters

    def _filter_entries(self, filters: dict[str, Any]) -> list[DiscoveryEntry]:
        entries = self.entries
        engine = self._first(filters.get("search_engine"))
        category = self._first(filters.get("category"))
        tags = {str(tag).lower() for tag in filters.get("tags", [])}
        if engine:
            entries = [entry for entry in entries if entry.search_engine.lower() == engine.lower()]
        if category:
            entries = [entry for entry in entries if entry.category.lower() == category.lower()]
        if tags:
            entries = [entry for entry in entries if tags.intersection({tag.lower() for tag in entry.tags})]
        return entries

    def _keyword_score(self, entry: DiscoveryEntry, terms: list[str]) -> tuple[float, list[str]]:
        if not terms:
            return 0.1, []
        text = entry.searchable_text().lower()
        counts = Counter(term for term in terms if term in text)
        matched = sorted(counts)
        if not matched:
            return 0.0, []
        coverage = len(matched) / len(set(terms))
        density = min(1.0, sum(counts.values()) / max(3.0, math.sqrt(len(text.split()) or 1)))
        return round(0.80 * coverage + 0.20 * density, 6), matched

    def _terms(self, query: str) -> list[str]:
        stopwords = {"the", "and", "for", "with", "from", "query", "search", "dork"}
        normalized = "".join(ch.lower() if ch.isalnum() or ch in {"-", "_", ":"} else " " for ch in query)
        return [term for term in normalized.split() if len(term) > 2 and term not in stopwords]

    def _first(self, value: Any) -> str:
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value or "")
