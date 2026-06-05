from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from context.embeddings import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity
from memory.schema import MemoryCollection, MemoryRecord, MemorySearchResult


class MemoryVectorStore(Protocol):
    def ensure_collection(self, collection: MemoryCollection) -> None:
        ...

    def upsert(self, record: MemoryRecord, vector: tuple[float, ...]) -> None:
        ...

    def exists_by_hash(self, collection: MemoryCollection, content_hash: str) -> bool:
        ...

    def search(
        self,
        collection: MemoryCollection,
        vector: tuple[float, ...],
        *,
        limit: int,
    ) -> tuple[MemorySearchResult, ...]:
        ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self.loaded_collections: set[MemoryCollection] = set()
        self._vectors: dict[MemoryCollection, dict[str, tuple[float, ...]]] = {}
        self._records: dict[MemoryCollection, dict[str, MemoryRecord]] = {}
        self._hashes: dict[MemoryCollection, set[str]] = {}

    def ensure_collection(self, collection: MemoryCollection) -> None:
        self.loaded_collections.add(collection)
        self._vectors.setdefault(collection, {})
        self._records.setdefault(collection, {})
        self._hashes.setdefault(collection, set())

    def upsert(self, record: MemoryRecord, vector: tuple[float, ...]) -> None:
        self.ensure_collection(record.collection)
        self._records[record.collection][record.id] = record
        self._vectors[record.collection][record.id] = vector
        self._hashes[record.collection].add(record.content_hash)

    def exists_by_hash(self, collection: MemoryCollection, content_hash: str) -> bool:
        self.ensure_collection(collection)
        return bool(content_hash and content_hash in self._hashes[collection])

    def search(
        self,
        collection: MemoryCollection,
        vector: tuple[float, ...],
        *,
        limit: int,
    ) -> tuple[MemorySearchResult, ...]:
        self.ensure_collection(collection)
        scored = [
            MemorySearchResult(record=self._records[collection][record_id], score=cosine_similarity(vector, stored))
            for record_id, stored in self._vectors[collection].items()
        ]
        scored.sort(key=lambda item: (-item.score, item.record.source, item.record.id))
        return tuple(scored[: max(1, int(limit))])


class QdrantMemoryStore:
    """Qdrant adapter for unified ANUBIS memory collections."""

    def __init__(
        self,
        *,
        url: str = "http://localhost:6333",
        dimensions: int = 128,
        collection_prefix: str = "",
        client: object | None = None,
    ) -> None:
        self.dimensions = dimensions
        self.collection_prefix = collection_prefix
        self.loaded_collections: set[MemoryCollection] = set()
        if client is not None:
            self.client = client
        else:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:  # pragma: no cover - deployment dependency guard
                raise RuntimeError("qdrant-client is required for QdrantMemoryStore") from exc
            self.client = QdrantClient(url=url)

    def collection_name(self, collection: MemoryCollection) -> str:
        return f"{self.collection_prefix}{collection.value}"

    def ensure_collection(self, collection: MemoryCollection) -> None:
        if collection in self.loaded_collections:
            return
        try:
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("qdrant-client is required for QdrantMemoryStore") from exc
        name = self.collection_name(collection)
        if not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE),
            )
        self.loaded_collections.add(collection)

    def upsert(self, record: MemoryRecord, vector: tuple[float, ...]) -> None:
        try:
            from qdrant_client.models import PointStruct
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("qdrant-client is required for QdrantMemoryStore") from exc
        self.ensure_collection(record.collection)
        self.client.upsert(
            collection_name=self.collection_name(record.collection),
            points=[
                PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"{record.collection.value}:{record.id}")),
                    vector=list(vector),
                    payload=record.to_dict(),
                )
            ],
        )

    def exists_by_hash(self, collection: MemoryCollection, content_hash: str) -> bool:
        if not content_hash:
            return False
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("qdrant-client is required for QdrantMemoryStore") from exc
        self.ensure_collection(collection)
        result = self.client.scroll(
            collection_name=self.collection_name(collection),
            scroll_filter=Filter(must=[FieldCondition(key="content_hash", match=MatchValue(value=content_hash))]),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        points = result[0] if isinstance(result, tuple) else result
        return bool(points)

    def search(
        self,
        collection: MemoryCollection,
        vector: tuple[float, ...],
        *,
        limit: int,
    ) -> tuple[MemorySearchResult, ...]:
        self.ensure_collection(collection)
        response = self.client.query_points(
            collection_name=self.collection_name(collection),
            query=list(vector),
            limit=max(1, int(limit)),
            with_payload=True,
        )
        return tuple(
            MemorySearchResult(record=_record_from_payload(dict(point.payload or {}), collection), score=float(point.score))
            for point in response.points
        )


class MemoryEmbedder:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or HashEmbeddingProvider()
        self._cache: dict[str, tuple[float, ...]] = {}

    @property
    def dimensions(self) -> int:
        return len(self.embed("__dimension_probe__"))

    def embed(self, text: str) -> tuple[float, ...]:
        if text not in self._cache:
            self._cache[text] = self.provider.embed(text)
        return self._cache[text]

    def embed_many(self, texts: Iterable[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed(text) for text in texts)


def _record_from_payload(payload: dict[str, object], fallback_collection: MemoryCollection) -> MemoryRecord:
    collection = MemoryCollection(str(payload.get("collection") or fallback_collection.value))
    return MemoryRecord(
        id=str(payload.get("id") or ""),
        collection=collection,
        text=str(payload.get("text") or ""),
        source=str(payload.get("source") or ""),
        metadata=dict(payload.get("metadata") or {}),
        content_hash=str(payload.get("content_hash") or ""),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
    )


__all__ = [
    "InMemoryMemoryStore",
    "MemoryEmbedder",
    "MemoryVectorStore",
    "QdrantMemoryStore",
]
