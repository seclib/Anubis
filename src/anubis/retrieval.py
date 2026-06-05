from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from math import sqrt
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from anubis.memory import MemoryAccess, MemoryRecord, MemoryScope, SearchResult, SharedMemory


class QueryRoute(StrEnum):
    SCOPED = "scoped"
    GLOBAL = "global"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class Embedding:
    text: str
    vector: tuple[float, ...]
    model: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))


class Embedder:
    def embed(self, text: str) -> Embedding:
        raise NotImplementedError

    def embed_many(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(self.embed(text) for text in texts)


class HashingEmbedder(Embedder):
    """Deterministic offline embedding provider for local-first retrieval."""

    def __init__(self, *, dimensions: int = 64, model: str = "hashing-v1") -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")
        self.dimensions = dimensions
        self.model = model

    def embed(self, text: str) -> Embedding:
        vector = [0.0] * self.dimensions
        for token, count in Counter(_tokenize(text)).items():
            vector[_stable_hash(token) % self.dimensions] += float(count)
        return Embedding(text=text, vector=_normalize(vector), model=self.model)


class VectorDatabase:
    def upsert(self, record: MemoryRecord, embedding: Embedding) -> None:
        raise NotImplementedError

    def delete(self, memory_id: str) -> None:
        raise NotImplementedError

    def search(
        self,
        embedding: Embedding,
        access: MemoryAccess,
        *,
        limit: int,
    ) -> tuple[SearchResult, ...]:
        raise NotImplementedError

    def sync_from_memory(self, memory: SharedMemory, *, after_cursor: int = 0) -> int:
        raise NotImplementedError


class SharedMemoryVectorDB(VectorDatabase):
    """Vector DB adapter backed by SharedMemory's local vector index."""

    def __init__(self, memory: SharedMemory) -> None:
        self.memory = memory

    def upsert(self, record: MemoryRecord, embedding: Embedding) -> None:
        self.memory.put(record, vector=embedding.vector)

    def delete(self, memory_id: str) -> None:
        self.memory.delete_vector(memory_id)

    def search(
        self,
        embedding: Embedding,
        access: MemoryAccess,
        *,
        limit: int,
    ) -> tuple[SearchResult, ...]:
        return self.memory.search(embedding.vector, access, limit=limit)

    def sync_from_memory(self, memory: SharedMemory, *, after_cursor: int = 0) -> int:
        return self.memory.apply_vector_sync(memory.vector_sync(after_cursor=after_cursor))


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    access: MemoryAccess
    route: QueryRoute = QueryRoute.HYBRID
    limit: int = 5
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    record: MemoryRecord
    score: float
    route: QueryRoute
    explanation: str


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    query: RetrievalQuery
    embedding_model: str
    route: QueryRoute
    results: tuple[RetrievalResult, ...]
    explanation: tuple[str, ...]


class QueryRouter:
    """Routes retrieval queries across scoped/global vector stores with isolation checks."""

    def __init__(
        self,
        *,
        scoped_db: VectorDatabase,
        embedder: Embedder | None = None,
        global_db: VectorDatabase | None = None,
    ) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.scoped_db = scoped_db
        self.global_db = global_db

    def index(self, record: MemoryRecord, *, db: QueryRoute = QueryRoute.SCOPED) -> Embedding:
        embedding = self.embedder.embed(_record_text(record))
        self._db_for_index(db).upsert(record, embedding)
        return embedding

    def query(self, query: RetrievalQuery) -> RetrievalResponse:
        embedding = self.embedder.embed(query.text)
        results: list[RetrievalResult] = []
        explanation = [
            f"Embedded query with model '{embedding.model}'.",
            f"Selected route '{query.route}'.",
        ]

        if query.route in {QueryRoute.SCOPED, QueryRoute.HYBRID}:
            scoped = self.scoped_db.search(embedding, query.access, limit=query.limit)
            results.extend(
                RetrievalResult(
                    record=item.record,
                    score=item.score,
                    route=QueryRoute.SCOPED,
                    explanation="Matched scoped memory allowed by isolation policy.",
                )
                for item in scoped
            )
            explanation.append(f"Scoped route returned {len(scoped)} candidate(s).")

        if query.route in {QueryRoute.GLOBAL, QueryRoute.HYBRID} and self.global_db is not None:
            global_results = self.global_db.search(
                embedding,
                self._global_access(query.access),
                limit=query.limit,
            )
            results.extend(
                RetrievalResult(
                    record=item.record,
                    score=item.score,
                    route=QueryRoute.GLOBAL,
                    explanation="Matched global memory allowed by isolation policy.",
                )
                for item in global_results
            )
            explanation.append(f"Global route returned {len(global_results)} candidate(s).")

        ranked = self._dedupe_and_rank(results, query.limit)
        explanation.append(f"Returned {len(ranked)} result(s) after deterministic ranking.")
        return RetrievalResponse(
            query=query,
            embedding_model=embedding.model,
            route=query.route,
            results=ranked,
            explanation=tuple(explanation),
        )

    def _db_for_index(self, route: QueryRoute) -> VectorDatabase:
        if route == QueryRoute.GLOBAL:
            if self.global_db is None:
                raise ValueError("global vector database is not configured")
            return self.global_db
        return self.scoped_db

    def _global_access(self, access: MemoryAccess) -> MemoryAccess:
        return MemoryAccess(
            actor_id=access.actor_id,
            scopes=frozenset({MemoryScope.GLOBAL}),
            max_sensitivity=access.max_sensitivity,
        )

    def _dedupe_and_rank(
        self,
        results: Sequence[RetrievalResult],
        limit: int,
    ) -> tuple[RetrievalResult, ...]:
        by_id: dict[str, RetrievalResult] = {}
        for result in results:
            current = by_id.get(result.record.id)
            if current is None or result.score > current.score:
                by_id[result.record.id] = result
        return tuple(
            sorted(by_id.values(), key=lambda item: (-item.score, item.route, item.record.id))[:limit]
        )


def _record_text(record: MemoryRecord) -> str:
    metadata = " ".join(f"{key}:{value}" for key, value in sorted(record.metadata.items()))
    return f"{record.content} {metadata}".strip()


def _tokenize(text: str) -> tuple[str, ...]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return tuple(token for token in normalized.split() if token)


def _stable_hash(text: str) -> int:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value ^= byte
        value *= 16777619
        value &= 0xFFFFFFFF
    return value


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(float(value) for value in vector)
    return tuple(float(value) / norm for value in vector)

