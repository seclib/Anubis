"""Qdrant collection manager and document indexing engine."""

from __future__ import annotations

from typing import Any

from memory import vector
from retrieval.embedding_pipeline import EmbeddingPipeline
from storage.qdrant import QdrantStore


class QdrantRetrievalEngine:
    def __init__(
        self,
        *,
        store: QdrantStore | None = None,
        embeddings: EmbeddingPipeline | None = None,
    ) -> None:
        self.store = store or QdrantStore()
        self.embeddings = embeddings or EmbeddingPipeline()

    def health(self) -> dict[str, Any]:
        return self.store.health()

    def ensure_ready(self, vector_size: int = 256, *, recreate: bool = False) -> dict[str, Any]:
        ok = self.store.ensure_collection(vector_size, recreate=recreate)
        return {
            "ok": ok,
            "collection": self.store.collection,
            "info": self.store.collection_info(),
            "payload_indexes": self.store.ensure_payload_indexes() if ok else {},
        }

    def index_local_vector_store(self, *, limit: int | None = None) -> dict[str, Any]:
        documents = [doc for doc in vector.load_vector_store().get("documents", []) if isinstance(doc, dict)]
        if limit is not None:
            documents = documents[: max(0, int(limit))]
        target_vector_size = len(self.embeddings.embed_query("qdrant vector size probe")["embedding"])
        points: list[dict[str, Any]] = []
        for doc in documents:
            text = str(doc.get("text") or "")
            source = str(doc.get("source") or "")
            if not text.strip():
                continue
            embedding = doc.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != target_vector_size:
                embedding = self.embeddings.embed_document(f"{source}\n{text}")["embedding"]
            payload = self._payload_from_doc(doc, text=text, source=source)
            points.append({"id": str(doc.get("id") or f"{source}:{len(points)}"), "vector": embedding, "payload": payload})
        if not points:
            return {"ok": False, "indexed": 0, "error": "no local vector documents"}
        result = self.store.upsert_many(points, vector_size=len(points[0]["vector"]))
        return {**result, "indexed": result.get("upserted", 0), "source_documents": len(documents)}

    def search(
        self,
        query: str,
        *,
        query_embedding: list[float] | None = None,
        top_k: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        embedding = query_embedding or self.embeddings.embed_query(query)["embedding"]
        return self.store.search(vector=embedding, top_k=top_k, filters=filters or {})

    def _payload_from_doc(self, doc: dict[str, Any], *, text: str, source: str) -> dict[str, Any]:
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        return {
            "chunk_id": doc.get("id"),
            "document_id": metadata.get("document_id") or source,
            "parent_id": metadata.get("parent_id"),
            "kind": doc.get("kind"),
            "source": source,
            "source_id": metadata.get("source_id") or source,
            "source_type": metadata.get("source_type") or doc.get("kind") or "local",
            "domain": metadata.get("domain") or "general",
            "title": metadata.get("title") or source,
            "path": metadata.get("path") or source,
            "url": metadata.get("url") or metadata.get("source_url"),
            "text": text[:4000],
            "quality_score": float(metadata.get("quality_score") or 0.0),
            "trust_score": float(metadata.get("trust_score") or 0.0),
            "freshness_score": float(metadata.get("freshness_score") or 0.0),
            "updated_at": doc.get("updated_at"),
            "metadata": metadata,
        }


__all__ = ["QdrantRetrievalEngine"]
