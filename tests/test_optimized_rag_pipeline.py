import unittest
from unittest.mock import patch

from retrieval.embedding_pipeline import EmbeddingPipeline
from retrieval.optimized import ChunkDeduplicator, OptimizedRetriever, QueryRouter, optimized_retrieval_architecture
from retrieval.service import RetrievalService


class FakeQdrantEngine:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query, *, query_embedding=None, top_k=20, filters=None):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters or {}})
        return self.rows[:top_k]


class FakeKeywordIndex:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query, top_k=10, filters=None):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters or {}})
        return self.rows[:top_k]


class FakeCache:
    def health(self):
        return {"ok": True}

    def get_embedding(self, text, *, model, embedder):
        return {"embedding": embedder(text), "cache": {"hit": True}}

    def lookup_query(self, *args, **kwargs):
        return {"hit": False}

    def store_query(self, *args, **kwargs):
        return None


class OptimizedRAGPipelineTest(unittest.TestCase):
    def test_query_router_reduces_channel_fanout_for_truth_queries(self) -> None:
        route = QueryRouter().route("what is the canonical firewall procedure", top_k=8)

        self.assertEqual(route.intent, "procedural")
        self.assertEqual(route.channels, ("keyword", "qdrant"))
        self.assertEqual(route.candidate_limits["local_vector"], 0)
        self.assertLessEqual(route.candidate_limits["qdrant"], 16)

    def test_optimized_retriever_deduplicates_and_groups_chunks(self) -> None:
        qdrant = FakeQdrantEngine(
            [
                {
                    "score": 0.95,
                    "backend": "qdrant",
                    "source": "a.md",
                    "text": "Procedure alpha step one.",
                    "payload": {"document_id": "a", "chunk_id": "a:1"},
                },
                {
                    "score": 0.90,
                    "backend": "qdrant",
                    "source": "a.md",
                    "text": "Procedure alpha step one.",
                    "payload": {"document_id": "a", "chunk_id": "a:1"},
                },
                {
                    "score": 0.80,
                    "backend": "qdrant",
                    "source": "a.md",
                    "text": "Procedure alpha step two.",
                    "payload": {"document_id": "a", "chunk_id": "a:2"},
                },
                {
                    "score": 0.75,
                    "backend": "qdrant",
                    "source": "b.md",
                    "text": "Procedure beta.",
                    "payload": {"document_id": "b", "chunk_id": "b:1"},
                },
            ]
        )
        keyword = FakeKeywordIndex([])

        result = OptimizedRetriever(qdrant=qdrant, keyword=keyword, embeddings=EmbeddingPipeline(cache=FakeCache())).retrieve(
            query="canonical procedure alpha",
            rewritten_query="canonical procedure alpha",
            query_embedding=[1.0, 0.0, 0.0],
            top_k=3,
        )

        self.assertLessEqual(len(result["results"]), 3)
        self.assertEqual(len({item["payload"]["chunk_id"] for item in result["results"]}), len(result["results"]))
        self.assertLess(result["optimization"]["candidates_after_dedupe"], result["optimization"]["candidates_before_dedupe"])

    def test_semantic_route_skips_keyword_for_lower_latency_when_not_needed(self) -> None:
        qdrant = FakeQdrantEngine([{"score": 0.9, "backend": "qdrant", "source": "incident", "text": "similar incident pattern"}])
        keyword = FakeKeywordIndex([])
        with patch("retrieval.optimized.vector.load_vector_store", return_value={"documents": []}):
            OptimizedRetriever(qdrant=qdrant, keyword=keyword, embeddings=EmbeddingPipeline(cache=FakeCache())).retrieve(
                query="find similar incident patterns",
                rewritten_query="find similar incident patterns",
                query_embedding=[1.0],
                top_k=4,
            )

        self.assertEqual(len(qdrant.calls), 1)
        self.assertEqual(len(keyword.calls), 1)
        self.assertLessEqual(keyword.calls[0]["top_k"], 8)

    def test_service_uses_compact_context_and_exposes_architecture(self) -> None:
        rows = [
            {
                "score": 0.95,
                "backend": "qdrant",
                "source": f"doc-{index}",
                "text": "context token reduction " * 200,
                "payload": {"document_id": f"doc-{index}", "chunk_id": f"doc-{index}:1"},
            }
            for index in range(6)
        ]
        service = RetrievalService(
            qdrant=object(),
            keyword=FakeKeywordIndex([]),
            obsidian=object(),
            cache=FakeCache(),
            embeddings=EmbeddingPipeline(cache=FakeCache()),
            hybrid=OptimizedRetriever(
                qdrant=FakeQdrantEngine(rows),
                keyword=FakeKeywordIndex([]),
                embeddings=EmbeddingPipeline(cache=FakeCache()),
            ),
        )

        response = service.retrieve("context token reduction", top_k=5)

        self.assertLessEqual(len(response["context"]), 4000)
        self.assertIn("optimization", response["cache"])
        self.assertEqual(response["architecture"]["metrics_target"]["tokens"], "50% reduction by deduplication, group caps, and 4000-char context budget")

    def test_architecture_documents_required_optimizations(self) -> None:
        architecture = optimized_retrieval_architecture()

        self.assertTrue(any("deduplicate" in item for item in architecture.stages))
        self.assertTrue(any("embedding cache" in item for item in architecture.optimizations))
        self.assertIn("latency", architecture.metrics_target)

    def test_chunk_deduplicator_prefers_highest_score_duplicate(self) -> None:
        deduped = ChunkDeduplicator().dedupe(
            [
                {"score": 0.2, "source": "a", "text": "same text"},
                {"score": 0.9, "source": "a", "text": "same text"},
            ]
        )

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["score"], 0.9)


if __name__ == "__main__":
    unittest.main()
