"""Production-facing hybrid retrieval and ingestion service."""

from __future__ import annotations

from typing import Any

from llm.ollama import call_chat
from memory import vector
from retrieval.confidence import retrieval_confidence
from retrieval.context_builder import build_context
from retrieval.embedding_pipeline import EmbeddingPipeline
from retrieval.hybrid import HybridRetriever
from retrieval.query_planner import QueryPlanner
from retrieval.qdrant_engine import QdrantRetrievalEngine
from services.cache_manager import CacheManager, get_cache_manager
from storage.keyword_index import KeywordIndex
from storage.obsidian import ObsidianStore
from storage.qdrant import QdrantStore


class RetrievalService:
    def __init__(
        self,
        *,
        qdrant: QdrantStore | None = None,
        keyword: KeywordIndex | None = None,
        obsidian: ObsidianStore | None = None,
        cache: CacheManager | None = None,
        embeddings: EmbeddingPipeline | None = None,
        hybrid: HybridRetriever | None = None,
    ) -> None:
        self.qdrant = qdrant or QdrantStore()
        self.keyword = keyword or KeywordIndex()
        self.obsidian = obsidian or ObsidianStore()
        self.cache = cache or get_cache_manager()
        self.embeddings = embeddings or EmbeddingPipeline(cache=self.cache)
        self.qdrant_engine = QdrantRetrievalEngine(store=self.qdrant, embeddings=self.embeddings)
        self.hybrid = hybrid or HybridRetriever(
            qdrant=self.qdrant_engine,
            keyword=self.keyword,
            embeddings=self.embeddings,
        )
        self.planner = QueryPlanner()

    def health(self) -> dict[str, Any]:
        return {
            "qdrant": self.qdrant.health(),
            "obsidian": self.obsidian.health(),
            "cache": self.cache.health(),
            "local_vector_documents": len(vector.load_vector_store().get("documents", [])),
        }

    def ensure_qdrant(self, *, recreate: bool = False) -> dict[str, Any]:
        sample = self.embeddings.embed_query("anubis qdrant collection probe")["embedding"]
        return self.qdrant_engine.ensure_ready(vector_size=len(sample), recreate=recreate)

    def index_qdrant(self, *, limit: int | None = None) -> dict[str, Any]:
        return self.qdrant_engine.index_local_vector_store(limit=limit)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
        generate_answer: bool = False,
    ) -> dict[str, Any]:
        clean_query = str(query or "").strip()
        if not clean_query:
            return {"query": clean_query, "results": [], "confidence": {"score": 0.0, "level": "none"}}

        plan = self.planner.analyze(clean_query, filters=filters)
        rewritten = str(plan["rewritten_query"])
        embedding_result = self.embeddings.embed_query(rewritten)
        embedding = embedding_result["embedding"]
        cache = self.cache.lookup_query(
            clean_query,
            query_embedding=embedding,
            filters=plan["filters"],
            top_k=3,
        )
        cache_confidence = float(cache.get("confidence") or 0.0)
        strong_cache_hit = bool(cache.get("hit")) and (
            cache.get("hit_type") == "exact" or cache_confidence >= 0.94
        )
        if strong_cache_hit and not generate_answer:
            return self._cached_response(clean_query, cache, embedding_result)

        hybrid = self.hybrid.retrieve(
            query=clean_query,
            rewritten_query=rewritten,
            query_embedding=embedding,
            filters=plan["filters"],
            top_k=top_k,
        )
        final_results = hybrid["results"]
        context = build_context(final_results)
        confidence = retrieval_confidence(final_results)
        answer = None
        if generate_answer:
            answer = self._answer(clean_query, context, confidence)

        response = {
            "query": clean_query,
            "plan": plan,
            "cache": {
                "hit": False,
                "query_backend": cache.get("backend"),
                "query_hit_type": cache.get("hit_type"),
                "embedding": embedding_result.get("cache"),
                "hybrid_channels": hybrid.get("channels"),
            },
            "results": final_results,
            "context": context,
            "confidence": confidence,
            "answer": answer,
        }
        self.cache.store_query(
            clean_query,
            result=answer or "retrieval-only",
            context=context,
            metadata={"confidence": confidence, "top_k": top_k, "plan": plan},
            query_embedding=embedding,
            filters=plan["filters"],
        )
        return response

    def ingest(
        self,
        *,
        title: str,
        content: str,
        source_url: str | None = None,
        folder: str = "Ingested",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(metadata or {})
        if source_url:
            metadata["source_url"] = source_url
        body = self._markdown(title=title, content=content, metadata=metadata)
        note = self.obsidian.write_note(title=title, content=body, folder=folder)
        index = self.obsidian.index(force=False)
        return {"success": True, "note": note, "index": index}

    def _answer(self, query: str, context: str, confidence: dict[str, Any]) -> str:
        if not context.strip():
            return "I do not have enough retrieved evidence to answer reliably."
        prompt = (
            "Answer only from the retrieved evidence. Include citation numbers like [1]. "
            "If evidence is weak, say so.\n\n"
            f"Confidence: {confidence}\n\n"
            f"Question: {query}\n\n"
            f"Evidence:\n{context}"
        )
        return call_chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=1200)

    def _cached_response(
        self,
        query: str,
        cache: dict[str, Any],
        embedding_result: dict[str, Any],
    ) -> dict[str, Any]:
        entry = cache.get("entry") if isinstance(cache.get("entry"), dict) else {}
        matches = cache.get("matches") if isinstance(cache.get("matches"), list) else []
        context = str(entry.get("context") or "")
        return {
            "query": query,
            "cache": {
                "hit": True,
                "backend": cache.get("backend"),
                "hit_type": cache.get("hit_type"),
                "confidence": cache.get("confidence"),
                "embedding": embedding_result.get("cache"),
            },
            "results": matches,
            "context": context,
            "confidence": {"score": cache.get("confidence", 0.0), "level": "cached"},
            "answer": entry.get("result") if entry.get("result") != "retrieval-only" else None,
        }

    def _markdown(self, *, title: str, content: str, metadata: dict[str, Any]) -> str:
        source = metadata.get("source_url") or metadata.get("source") or "local-ingest"
        return (
            f"# {title}\n\n"
            f"- Source: {source}\n"
            "- Ingested by: Anubis retrieval service\n\n"
            "## Content\n\n"
            f"{content.strip()}\n"
        )


_SERVICE: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RetrievalService()
    return _SERVICE


__all__ = ["RetrievalService", "get_retrieval_service"]
