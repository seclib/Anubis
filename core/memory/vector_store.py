"""Abstracted deterministic vector retrieval primitives."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from math import sqrt
from types import MappingProxyType
from typing import Any, Mapping, Sequence


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class Embedding:
    text: str
    vector: tuple[float, ...]
    model: str = "hashing-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> Embedding:
        """Return a deterministic embedding for text."""


class HashingEmbedder(Embedder):
    """Small offline embedding provider with deterministic token hashing."""

    def __init__(self, *, dimensions: int = 64, model: str = "hashing-v1") -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.model = model

    def embed(self, text: str) -> Embedding:
        vector = [0.0] * self.dimensions
        for token, count in Counter(_tokenize(text)).items():
            vector[_stable_hash(token) % self.dimensions] += float(count)
        return Embedding(text=text, vector=_normalize(vector), model=self.model)


@dataclass(frozen=True, slots=True)
class VectorDocument:
    document_id: str
    text: str
    vector: tuple[float, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    sequence: int = 0

    def __post_init__(self) -> None:
        document_id = self.document_id.strip()
        text = self.text.strip()
        if not document_id:
            raise ValueError("document_id cannot be empty")
        if not text:
            raise ValueError("text cannot be empty")
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    document: VectorDocument
    score: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document.document_id,
            "score": self.score,
            "text": self.document.text,
            "metadata": dict(self.document.metadata),
            "explanation": self.explanation,
        }


class VectorStore(ABC):
    @abstractmethod
    def append(self, *, document_id: str, text: str, embedding: Embedding, metadata: Mapping[str, Any] | None = None) -> VectorDocument:
        """Append a vector document. Implementations must not overwrite existing entries."""

    @abstractmethod
    def search(self, embedding: Embedding, *, limit: int = 5) -> tuple[VectorSearchResult, ...]:
        """Search documents deterministically."""


class InMemoryVectorStore(VectorStore):
    """Append-only in-memory vector store for local deterministic retrieval."""

    def __init__(self) -> None:
        self._documents: list[VectorDocument] = []

    def append(
        self,
        *,
        document_id: str,
        text: str,
        embedding: Embedding,
        metadata: Mapping[str, Any] | None = None,
    ) -> VectorDocument:
        record = VectorDocument(
            document_id=document_id,
            text=text,
            vector=embedding.vector,
            metadata=metadata or {},
            sequence=len(self._documents) + 1,
        )
        self._documents.append(record)
        return record

    def all(self) -> tuple[VectorDocument, ...]:
        return tuple(self._documents)

    def search(self, embedding: Embedding, *, limit: int = 5) -> tuple[VectorSearchResult, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        results = [
            VectorSearchResult(
                document=document,
                score=round(_cosine(embedding.vector, document.vector), 6),
                explanation="Cosine similarity from deterministic hashing embeddings.",
            )
            for document in self._documents
        ]
        ranked = sorted(
            results,
            key=lambda result: (-result.score, result.document.sequence, result.document.document_id),
        )
        return tuple(ranked[:limit])


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


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have matching dimensions")
    return sum(a * b for a, b in zip(left, right))


__all__ = [
    "Embedder",
    "Embedding",
    "HashingEmbedder",
    "InMemoryVectorStore",
    "VectorDocument",
    "VectorSearchResult",
    "VectorStore",
]
