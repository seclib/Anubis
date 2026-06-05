from __future__ import annotations

from rag.discovery.schema import DiscoveryChunk, DiscoveryEntry
from rag.shared.embedding import EmbeddingPipeline


class DiscoveryEmbeddingPipeline:
    domain = "discovery"

    def __init__(self, embedder: EmbeddingPipeline | None = None) -> None:
        self.embedder = embedder or EmbeddingPipeline()

    def chunk_entry(self, entry: DiscoveryEntry) -> DiscoveryChunk:
        metadata = {
            "source": entry.source,
            "category": entry.category,
            "query": entry.query,
            "description": entry.description,
            "tags": list(entry.tags),
            "search_engine": entry.search_engine,
        }
        return DiscoveryChunk(
            chunk_id=f"{entry.doc_id}:query",
            doc_id=entry.doc_id,
            text=self._entry_text(entry),
            title=entry.title,
            source_uri=entry.source_uri,
            metadata=metadata,
        )

    def chunks_for_entries(self, entries: list[DiscoveryEntry]) -> list[DiscoveryChunk]:
        return [self.chunk_entry(entry) for entry in entries]

    def _entry_text(self, entry: DiscoveryEntry) -> str:
        return "\n".join(
            part
            for part in (
                f"Title: {entry.title}",
                f"Source: {entry.source}",
                f"Search engine: {entry.search_engine}",
                f"Category: {entry.category}",
                f"Query: {entry.query}",
                f"Description: {entry.description}",
                f"Tags: {', '.join(entry.tags)}",
            )
            if part and not part.endswith(": ")
        )
