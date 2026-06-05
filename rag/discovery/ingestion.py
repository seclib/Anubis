from __future__ import annotations

import logging
from pathlib import Path

from rag.discovery.embedding import DiscoveryEmbeddingPipeline
from rag.discovery.parser import DiscoveryParser
from rag.discovery.schema import DiscoveryEntry, write_jsonl
from rag.shared.qdrant_client import QdrantVectorStore


logger = logging.getLogger("anubis.rag.discovery.ingestion")


class DiscoveryIngestion:
    domain = "discovery"

    def __init__(
        self,
        parser: DiscoveryParser | None = None,
        embedding: DiscoveryEmbeddingPipeline | None = None,
        vector_store: QdrantVectorStore | None = None,
        index_path: str | Path = "state/discovery_index.jsonl",
    ) -> None:
        self.parser = parser or DiscoveryParser()
        self.embedding = embedding or DiscoveryEmbeddingPipeline()
        self.vector_store = vector_store or QdrantVectorStore(self.embedding.embedder)
        self.index_path = Path(index_path)

    def ingest(self, source_path: str | Path, batch_size: int = 64) -> dict[str, int | str]:
        entries = self.parser.parse_path(source_path)
        chunks = self.embedding.chunks_for_entries(entries)
        upserted = self.vector_store.upsert_chunks(
            self.domain,
            [chunk.to_vector_chunk() for chunk in chunks],
            batch_size=batch_size,
        )
        self.save_index(entries)
        logger.info("ingested discovery entries=%s chunks=%s upserted=%s", len(entries), len(chunks), upserted)
        return {
            "entries": len(entries),
            "chunks": len(chunks),
            "upserted": upserted,
            "index_path": str(self.index_path),
        }

    def save_index(self, entries: list[DiscoveryEntry]) -> None:
        write_jsonl(self.index_path, [entry.to_dict() for entry in entries])
