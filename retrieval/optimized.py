"""Optimized hierarchical retrieval for production RAG."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import re
from typing import Any, Literal

from memory import vector
from retrieval.embedding_pipeline import EmbeddingPipeline
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.qdrant_engine import QdrantRetrievalEngine
from storage.keyword_index import KeywordIndex


RetrievalChannel = Literal["qdrant", "local_vector", "keyword"]
RetrievalIntent = Literal["semantic", "truth", "procedural", "hybrid"]


TRUTH_TERMS = {"canonical", "current", "decision", "policy", "rule", "truth"}
PROCEDURE_TERMS = {"checklist", "how", "playbook", "procedure", "runbook", "steps", "workflow"}
SEMANTIC_TERMS = {"analogous", "example", "incident", "pattern", "recall", "related", "similar"}


@dataclass(frozen=True)
class RetrievalRoute:
    intent: RetrievalIntent
    channels: tuple[RetrievalChannel, ...]
    candidate_limits: dict[RetrievalChannel, int]
    final_limit: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalArchitecture:
    stages: tuple[str, ...]
    optimizations: tuple[str, ...]
    metrics_target: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueryRouter:
    def route(self, query: str, *, top_k: int, filters: dict[str, Any] | None = None) -> RetrievalRoute:
        tokens = _tokens(query)
        truth = bool(tokens & TRUTH_TERMS)
        procedure = bool(tokens & PROCEDURE_TERMS)
        semantic = bool(tokens & SEMANTIC_TERMS)
        domain = str((filters or {}).get("domain") or "")
        final_limit = max(1, min(int(top_k), 12))
        if truth or procedure:
            intent: RetrievalIntent = "procedural" if procedure else "truth"
            channels: tuple[RetrievalChannel, ...] = ("keyword", "qdrant")
            limits = {
                "keyword": _candidate_limit(final_limit, multiplier=4, floor=8, ceiling=28),
                "qdrant": _candidate_limit(final_limit, multiplier=2, floor=4, ceiling=16),
                "local_vector": 0,
            }
        elif semantic or domain not in {"", "general"}:
            intent = "semantic"
            channels = ("qdrant", "local_vector")
            limits = {
                "qdrant": _candidate_limit(final_limit, multiplier=4, floor=8, ceiling=28),
                "local_vector": _candidate_limit(final_limit, multiplier=3, floor=6, ceiling=24),
                "keyword": _candidate_limit(final_limit, multiplier=1, floor=3, ceiling=8),
            }
        else:
            intent = "hybrid"
            channels = ("qdrant", "keyword", "local_vector")
            limits = {
                "qdrant": _candidate_limit(final_limit, multiplier=3, floor=6, ceiling=24),
                "keyword": _candidate_limit(final_limit, multiplier=2, floor=4, ceiling=16),
                "local_vector": _candidate_limit(final_limit, multiplier=2, floor=4, ceiling=16),
            }
        return RetrievalRoute(intent=intent, channels=channels, candidate_limits=limits, final_limit=final_limit)


class ChunkDeduplicator:
    def dedupe(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_key: dict[str, dict[str, Any]] = {}
        for item in results:
            key = self.key(item)
            existing = best_by_key.get(key)
            if existing is None or _result_score(item) > _result_score(existing):
                best_by_key[key] = item
        deduped = list(best_by_key.values())
        deduped.sort(key=_result_score, reverse=True)
        return deduped

    def key(self, item: dict[str, Any]) -> str:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        stable_id = payload.get("chunk_id") or item.get("id")
        if stable_id:
            return f"id:{stable_id}"
        text = _text(item)
        source = str(item.get("source") or payload.get("source") or payload.get("path") or "")
        normalized = " ".join(text.split()).lower()[:600]
        return sha256(f"{source}\n{normalized}".encode("utf-8", errors="ignore")).hexdigest()


class HierarchicalRanker:
    def select(self, results: list[dict[str, Any]], *, limit: int, max_chunks_per_group: int = 2) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            groups.setdefault(self.group_key(item), []).append(item)
        ranked_groups = sorted(groups.values(), key=lambda group: max(_result_score(item) for item in group), reverse=True)
        selected: list[dict[str, Any]] = []
        for group in ranked_groups:
            group.sort(key=_result_score, reverse=True)
            selected.extend(group[:max(1, max_chunks_per_group)])
            if len(selected) >= limit:
                break
        selected.sort(key=_result_score, reverse=True)
        return selected[: max(1, limit)]

    def group_key(self, item: dict[str, Any]) -> str:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        for key in ("parent_id", "document_id", "source_id", "path", "source", "url"):
            value = payload.get(key) or item.get(key)
            if value:
                return str(value)
        return self._coarse_text_key(item)

    def _coarse_text_key(self, item: dict[str, Any]) -> str:
        text = _text(item)
        return sha256(" ".join(text.split()).lower()[:240].encode("utf-8", errors="ignore")).hexdigest()


class OptimizedRetriever:
    def __init__(
        self,
        *,
        qdrant: QdrantRetrievalEngine | None = None,
        keyword: KeywordIndex | None = None,
        embeddings: EmbeddingPipeline | None = None,
        router: QueryRouter | None = None,
        deduplicator: ChunkDeduplicator | None = None,
        ranker: HierarchicalRanker | None = None,
    ) -> None:
        self.embeddings = embeddings or EmbeddingPipeline()
        self.qdrant = qdrant or QdrantRetrievalEngine(embeddings=self.embeddings)
        self.keyword = keyword or KeywordIndex()
        self.router = router or QueryRouter()
        self.deduplicator = deduplicator or ChunkDeduplicator()
        self.ranker = ranker or HierarchicalRanker()

    def retrieve(
        self,
        *,
        query: str,
        rewritten_query: str,
        query_embedding: list[float],
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        route = self.router.route(rewritten_query or query, top_k=top_k, filters=filters or {})
        qdrant_results = self._qdrant(rewritten_query, query_embedding, filters or {}, route)
        keyword_results = self._keyword(query, filters or {}, route)
        local_results = self._local_semantic_search(rewritten_query, query_embedding, route)
        fused = reciprocal_rank_fusion([qdrant_results, local_results, keyword_results])
        deduped = self.deduplicator.dedupe(fused)
        final_results = self.ranker.select(deduped, limit=route.final_limit)
        before = sum(len(items) for items in (qdrant_results, local_results, keyword_results))
        return {
            "results": final_results,
            "channels": {
                "qdrant": len(qdrant_results),
                "local_vector": len(local_results),
                "keyword": len(keyword_results),
            },
            "optimization": {
                "route": route.to_dict(),
                "candidates_before_dedupe": before,
                "candidates_after_dedupe": len(deduped),
                "final_results": len(final_results),
                "estimated_latency_reduction": "50% target via routed channel fanout and lower candidate_k",
                "estimated_token_reduction": "50% target via hierarchical group caps and shorter context",
            },
        }

    def _qdrant(
        self,
        query: str,
        query_embedding: list[float],
        filters: dict[str, Any],
        route: RetrievalRoute,
    ) -> list[dict[str, Any]]:
        limit = route.candidate_limits.get("qdrant", 0)
        if limit <= 0 or "qdrant" not in route.channels:
            return []
        return self.qdrant.search(query, query_embedding=query_embedding, top_k=limit, filters=filters)

    def _keyword(self, query: str, filters: dict[str, Any], route: RetrievalRoute) -> list[dict[str, Any]]:
        limit = route.candidate_limits.get("keyword", 0)
        if limit <= 0:
            return []
        if "keyword" not in route.channels and route.intent != "semantic":
            return []
        return self.keyword.search(query, top_k=limit, filters=filters)

    def _local_semantic_search(
        self,
        query: str,
        query_embedding: list[float],
        route: RetrievalRoute,
    ) -> list[dict[str, Any]]:
        limit = route.candidate_limits.get("local_vector", 0)
        if limit <= 0 or "local_vector" not in route.channels:
            return []
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
            metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            results.append(
                {
                    "score": round(score, 6),
                    "kind": doc.get("kind"),
                    "source": doc.get("source"),
                    "chunk_index": doc.get("chunk_index"),
                    "text": doc.get("text", ""),
                    "metadata": metadata,
                    "payload": metadata,
                    "backend": "local_vector",
                }
            )
        results.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return results[:limit]


def optimized_retrieval_architecture() -> RetrievalArchitecture:
    return RetrievalArchitecture(
        stages=(
            "classify query intent and route to minimal retrieval channels",
            "optimize candidate top-k per channel before search",
            "fuse channel results with reciprocal rank fusion",
            "deduplicate chunks by stable ids and normalized text hashes",
            "rank parent/document groups and keep only best chunks per group",
            "build compact context from final hierarchical results",
        ),
        optimizations=(
            "semantic queries prioritize Qdrant/local vectors",
            "truth/procedural queries prioritize keyword/Obsidian evidence",
            "embedding cache is reused through EmbeddingPipeline and CacheManager",
            "duplicate chunks are collapsed before context rendering",
            "final context receives grouped top-k instead of raw flat candidate lists",
        ),
        metrics_target={
            "latency": "50% reduction by reducing channel fanout and candidate_k",
            "tokens": "50% reduction by deduplication, group caps, and 4000-char context budget",
        },
    )


def _candidate_limit(top_k: int, *, multiplier: int, floor: int, ceiling: int) -> int:
    return max(floor, min(int(top_k) * multiplier, ceiling))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_.:-]{3,}", str(text).lower())}


def _text(item: dict[str, Any]) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return str(item.get("text") or item.get("content") or item.get("markdown") or payload.get("text") or "")


def _result_score(item: dict[str, Any]) -> float:
    return float(item.get("final_score") or item.get("rrf_score") or item.get("score") or 0.0)


__all__ = [
    "ChunkDeduplicator",
    "HierarchicalRanker",
    "OptimizedRetriever",
    "QueryRouter",
    "RetrievalArchitecture",
    "RetrievalRoute",
    "optimized_retrieval_architecture",
]
