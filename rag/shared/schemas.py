from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Protocol


class VectorChunk(Protocol):
    chunk_id: str
    doc_id: str
    domain: str
    text: str
    source_uri: str
    title: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class VectorChunkRecord:
    chunk_id: str
    doc_id: str
    domain: str
    text: str
    source_uri: str
    title: str
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["VectorChunk", "VectorChunkRecord"]
