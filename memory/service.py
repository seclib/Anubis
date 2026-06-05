from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from memory.schema import (
    MemoryCollection,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    MemoryWriteResult,
    now_iso,
)
from memory.store import InMemoryMemoryStore, MemoryEmbedder, MemoryVectorStore


class UnifiedMemoryService:
    """Collection-aware memory service for repo, docs, and conversation recall."""

    def __init__(
        self,
        *,
        store: MemoryVectorStore | None = None,
        embedder: MemoryEmbedder | None = None,
    ) -> None:
        self.store = store or InMemoryMemoryStore()
        self.embedder = embedder or MemoryEmbedder()
        self._loaded_collections: set[MemoryCollection] = set()

    @property
    def loaded_collections(self) -> tuple[MemoryCollection, ...]:
        return tuple(sorted(self._loaded_collections, key=lambda item: item.value))

    def remember(
        self,
        collection: MemoryCollection | str,
        text: str,
        *,
        source: str,
        metadata: dict[str, Any] | None = None,
        record_id: str | None = None,
    ) -> MemoryWriteResult:
        record = self._record(collection, text, source=source, metadata=metadata, record_id=record_id)
        return self.store_records([record])

    def store_records(self, records: Iterable[MemoryRecord]) -> MemoryWriteResult:
        inserted = 0
        deduplicated = 0
        ids: list[str] = []
        for record in records:
            if not record.text.strip():
                continue
            self._ensure_loaded(record.collection)
            if self.store.exists_by_hash(record.collection, record.content_hash):
                deduplicated += 1
                continue
            self.store.upsert(record, self.embedder.embed(record.text))
            inserted += 1
            ids.append(record.id)
        return MemoryWriteResult(inserted=inserted, deduplicated=deduplicated, ids=tuple(ids))

    def retrieve(
        self,
        query: str | MemorySearchQuery,
        *,
        collections: Iterable[MemoryCollection | str] | None = None,
        limit: int = 5,
        min_score: float = 0.0,
    ) -> tuple[MemorySearchResult, ...]:
        request = self._query(query, collections=collections, limit=limit, min_score=min_score)
        if not request.query.strip():
            return ()
        query_vector = self.embedder.embed(request.query)
        per_collection_limit = max(1, request.limit)
        results: list[MemorySearchResult] = []
        for collection in request.collections:
            self._ensure_loaded(collection)
            results.extend(self.store.search(collection, query_vector, limit=per_collection_limit))
        filtered = [result for result in results if result.score >= request.min_score]
        deduped = self._dedupe_results(filtered)
        deduped.sort(key=lambda item: (-item.score, item.record.collection.value, item.record.source, item.record.id))
        return tuple(deduped[: max(1, request.limit)])

    def retrieve_payloads(
        self,
        query: str,
        *,
        collections: Iterable[MemoryCollection | str] | None = None,
        limit: int = 5,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        return [
            result.to_dict()
            for result in self.retrieve(query, collections=collections, limit=limit, min_score=min_score)
        ]

    def _ensure_loaded(self, collection: MemoryCollection) -> None:
        if collection in self._loaded_collections:
            return
        self.store.ensure_collection(collection)
        self._loaded_collections.add(collection)

    def _record(
        self,
        collection: MemoryCollection | str,
        text: str,
        *,
        source: str,
        metadata: dict[str, Any] | None,
        record_id: str | None,
    ) -> MemoryRecord:
        normalized_collection = normalize_collection(collection)
        normalized_text = str(text).strip()
        content_hash = memory_hash(normalized_text)
        generated_id = str(uuid5(NAMESPACE_URL, f"{normalized_collection.value}:{source}:{content_hash}"))
        timestamp = now_iso()
        return MemoryRecord(
            id=record_id or generated_id,
            collection=normalized_collection,
            text=normalized_text,
            source=str(source),
            metadata=dict(metadata or {}),
            content_hash=content_hash,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _query(
        self,
        query: str | MemorySearchQuery,
        *,
        collections: Iterable[MemoryCollection | str] | None,
        limit: int,
        min_score: float,
    ) -> MemorySearchQuery:
        if isinstance(query, MemorySearchQuery):
            return query
        selected = tuple(normalize_collection(collection) for collection in collections) if collections else tuple(MemoryCollection)
        return MemorySearchQuery(
            query=str(query),
            collections=selected,
            limit=max(1, int(limit)),
            min_score=max(0.0, float(min_score)),
        )

    def _dedupe_results(self, results: Iterable[MemorySearchResult]) -> list[MemorySearchResult]:
        best_by_hash: dict[tuple[MemoryCollection, str], MemorySearchResult] = {}
        for result in results:
            key = (result.record.collection, result.record.content_hash or memory_hash(result.record.text))
            existing = best_by_hash.get(key)
            if existing is None or result.score > existing.score:
                best_by_hash[key] = result
        return list(best_by_hash.values())


def normalize_collection(collection: MemoryCollection | str) -> MemoryCollection:
    if isinstance(collection, MemoryCollection):
        return collection
    if isinstance(collection, str):
        return MemoryCollection(collection)
    value = getattr(collection, "value", None)
    if value is not None:
        return MemoryCollection(str(value))
    name = getattr(collection, "name", None)
    if name is not None:
        return MemoryCollection[str(name)]
    return MemoryCollection(str(collection))


def memory_hash(text: str) -> str:
    normalized = " ".join(str(text).strip().split()).lower()
    return sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


__all__ = [
    "UnifiedMemoryService",
    "memory_hash",
    "normalize_collection",
]
