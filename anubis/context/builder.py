from __future__ import annotations

from pathlib import Path

from anubis.context.compressor.compressor import ContextCompressor
from anubis.context.embeddings import EmbeddingProvider
from anubis.context.indexer.indexer import RepositoryIndexer
from anubis.context.retriever.retriever import HybridContextRetriever
from anubis.context.schema import BuiltContext, RepositoryIndex


class ContextBuilder:
    def __init__(
        self,
        root: Path | str,
        embedding_provider: EmbeddingProvider | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.indexer = RepositoryIndexer(self.root, embedding_provider)
        self.retriever = HybridContextRetriever(embedding_provider)
        self.compressor = compressor or ContextCompressor()

    def build(self, task: str, top_k: int = 8, index: RepositoryIndex | None = None) -> BuiltContext:
        repository_index = index or self.indexer.index_repository()
        retrieved = self.retriever.retrieve(repository_index, task, top_k=top_k)
        context_chunks, summary = self.compressor.compress(task, retrieved)
        return BuiltContext(task=task, context_chunks=context_chunks, summary=summary)


__all__ = ["ContextBuilder"]
