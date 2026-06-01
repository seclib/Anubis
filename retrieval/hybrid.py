"""Hybrid retrieval across Qdrant, local vectors, and keyword index."""

from __future__ import annotations

from typing import Any

from memory import vector
from retrieval.embedding_pipeline import EmbeddingPipeline
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.qdrant_engine import QdrantRetrievalEngine
from storage.keyword_index import KeywordIndex


class HybridRetriever:
    def __init__(
        self,
        *,
        qdrant: QdrantRetrievalEngine | None = None,
        keyword: KeywordIndex | None = None,
        embeddings: EmbeddingPipeline | None = None,
    ) -> None:
        self.embeddings = embeddings or EmbeddingPipeline()
        self.qdrant = qdrant or QdrantRetrievalEngine(embeddings=self.embeddings)
        self.keyword = keyword or KeywordIndex()

    def retrieve(
        self,
        *,
        query: str,
        rewritten_query: str,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        candidate_k = max(20, top_k * 8)
        qdrant_results = self.qdrant.search(
            rewritten_query,
            query_embedding=query_embedding,
            top_k=candidate_k,
            filters=filters or {},
        )
        local_results = self._local_semantic_search(rewritten_query, query_embedding, top_k=candidate_k)
        keyword_results = self.keyword.search(query, top_k=candidate_k, filters=filters or {})
        normalized_local = [
            {
                **item,
                "backend": "local_vector",
                "payload": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            }
            for item in local_results
        ]
        fused = reciprocal_rank_fusion([qdrant_results, normalized_local, keyword_results])
        return {
            "results": fused[: max(1, min(int(top_k), 50))],
            "channels": {
                "qdrant": len(qdrant_results),
                "local_vector": len(local_results),
                "keyword": len(keyword_results),
            },
        }

    def _local_semantic_search(
        self,
        query: str,
        query_embedding: list[float],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for doc in vector.load_vector_store().get("documents", []):
            if not isinstance(doc, dict):
                continue
            embedding = doc.get("embedding")
            if not isinstance(embedding, list):
                continue
            score = vector._cosine(query_embedding, [float(value) for value in embedding])
            if score <= 0:
                continue
            results.append(
                {
                    "score": round(score, 6),
                    "kind": doc.get("kind"),
                    "source": doc.get("source"),
                    "chunk_index": doc.get("chunk_index"),
                    "text": doc.get("text", ""),
                    "metadata": doc.get("metadata", {}),
                }
            )
        results.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return results[: max(1, int(top_k))]


__all__ = ["HybridRetriever"]
