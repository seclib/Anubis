from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MemoryCollection(str, Enum):
    REPO = "repo"
    DOCS = "docs"
    CONVERSATIONS = "conversations"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    collection: MemoryCollection
    text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collection"] = self.collection.value
        return payload


@dataclass(frozen=True)
class MemorySearchQuery:
    query: str
    collections: tuple[MemoryCollection, ...] = (
        MemoryCollection.REPO,
        MemoryCollection.DOCS,
        MemoryCollection.CONVERSATIONS,
    )
    limit: int = 5
    min_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collections"] = [collection.value for collection in self.collections]
        return payload


@dataclass(frozen=True)
class MemorySearchResult:
    record: MemoryRecord
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, **self.record.to_dict()}


@dataclass(frozen=True)
class MemoryWriteResult:
    inserted: int = 0
    deduplicated: int = 0
    ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MigrationPlan:
    collections: tuple[MemoryCollection, ...]
    sources: tuple[str, ...]
    steps: tuple[str, ...]
    safety_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collections"] = [collection.value for collection in self.collections]
        return payload


__all__ = [
    "MemoryCollection",
    "MemoryRecord",
    "MemorySearchQuery",
    "MemorySearchResult",
    "MemoryWriteResult",
    "MigrationPlan",
    "now_iso",
]
