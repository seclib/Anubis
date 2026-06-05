from __future__ import annotations

from typing import Protocol


class VectorChunk(Protocol):
    chunk_id: str
    doc_id: str
    domain: str
    text: str
    source_uri: str
    title: str
    metadata: dict[str, object]
