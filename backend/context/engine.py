from __future__ import annotations

from pathlib import Path

from backend.context.compressor import CompressedContext, ContextCompressor
from backend.context.indexer import IndexStats, RepositoryIndexer
from backend.context.retriever import ContextRetriever, RetrievedChunk


class ContextEngine:
    def __init__(
        self,
        root: Path | None = None,
        index_path: Path | None = None,
        *,
        indexer: RepositoryIndexer | None = None,
        retriever: ContextRetriever | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self.indexer = indexer or RepositoryIndexer(root=root, index_path=index_path)
        self.retriever = retriever or ContextRetriever(
            root=self.indexer.root,
            index_path=self.indexer.index_path,
            indexer=self.indexer,
        )
        self.compressor = compressor or ContextCompressor()

    def index_repository(self) -> IndexStats:
        return self.indexer.index()

    def retrieve(self, task: str, top_k: int = 8) -> list[RetrievedChunk]:
        return self.retriever.retrieve(task, top_k=top_k)

    def context_for_task(self, task: str, top_k: int = 8) -> CompressedContext:
        chunks = self.retrieve(task, top_k=top_k)
        return self.compressor.compress(task, chunks)


__all__ = ["ContextEngine"]
