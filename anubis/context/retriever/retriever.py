from __future__ import annotations

from anubis.context.embeddings import EmbeddingCache, EmbeddingProvider, cosine_similarity
from anubis.context.query import expand_task_query
from anubis.context.schema import RepositoryIndex, RetrievedContext
from anubis.context.scoring import ContextScorer


class HybridContextRetriever:
    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.embedding_cache = EmbeddingCache(embedding_provider)

    def retrieve(self, index: RepositoryIndex, task: str, top_k: int = 8) -> tuple[RetrievedContext, ...]:
        expanded_query, terms = expand_task_query(task)
        query_embedding = self.embedding_cache.embed(expanded_query or task)
        scorer = ContextScorer(index.files)
        results: list[RetrievedContext] = []
        for embedded in index.chunks:
            semantic = cosine_similarity(query_embedding, embedded.embedding)
            total, keyword, importance, symbol = scorer.score(
                task=task,
                chunk=embedded.chunk,
                semantic_score=semantic,
                expanded_terms=terms,
            )
            if total <= 0:
                continue
            results.append(
                RetrievedContext(
                    chunk=embedded.chunk,
                    score=total,
                    semantic_score=round(semantic, 6),
                    keyword_score=keyword,
                    file_importance=importance,
                    symbol_score=symbol,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return tuple(results[: max(1, top_k)])


__all__ = ["HybridContextRetriever"]
