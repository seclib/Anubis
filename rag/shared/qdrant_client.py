from __future__ import annotations

import logging
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, FieldCondition, Filter, MatchAny, PointStruct, VectorParams
except Exception:  # pragma: no cover - dependency may be absent in local bootstrap
    QdrantClient = None
    Distance = FieldCondition = Filter = MatchAny = PointStruct = VectorParams = None

from rag.shared.embedding import EmbeddingService
from rag.shared.schemas import VectorChunk
from rag.shared.config import collection_name, config


logger = logging.getLogger("anubis.vector_db")
_MEMORY_POINTS: dict[str, list[dict[str, object]]] = {}
_FALLBACK_PATH = Path("state/rag_vector_fallback.json")


class QdrantVectorStore:
    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        self.embedder = embedder or EmbeddingService()
        self.client = QdrantClient(url=config.qdrant_url) if QdrantClient else None
        self._load_fallback()

    def ensure_collection(self, domain: str) -> str:
        name = collection_name(domain)
        if not self.client:
            return name
        try:
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
                )
        except Exception as exc:
            logger.warning("Qdrant unavailable for %s; using memory fallback: %s", name, exc)
        return name

    def upsert_chunks(self, domain: str, chunks: list[VectorChunk], batch_size: int = 64) -> int:
        if not chunks:
            return 0
        vectors = self.embedder.embed_batch([chunk.text for chunk in chunks], batch_size=batch_size)
        collection = self.ensure_collection(domain)
        points: list[PointStruct] = []
        memory_points = _MEMORY_POINTS.setdefault(collection, [])
        for chunk, vector in zip(chunks, vectors):
            point_id = str(uuid5(NAMESPACE_URL, chunk.chunk_id))
            payload = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "domain": chunk.domain,
                "text": chunk.text,
                "source_uri": chunk.source_uri,
                "title": chunk.title,
                **chunk.metadata,
            }
            if PointStruct:
                points.append(PointStruct(id=point_id, vector=vector, payload=payload))
            memory_points.append({"id": point_id, "vector": vector, "payload": payload})
        self._save_fallback()
        if not self.client:
            return len(chunks)
        try:
            self.client.upsert(collection_name=collection, points=points)
        except Exception as exc:
            logger.warning("Qdrant upsert failed for %s; memory fallback retained: %s", collection, exc)
        return len(chunks)

    def search(self, domain: str, query: str, top_k: int = 6, filters: dict[str, object] | None = None) -> list[dict[str, object]]:
        vector = self.embedder.embed(query)
        collection = self.ensure_collection(domain)
        query_filter = self._to_qdrant_filter(filters or {})
        if not self.client:
            return self._memory_search(collection, vector, domain, top_k, filters or {})
        try:
            response = self.client.query_points(
                collection_name=collection,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return [
                {"score": float(point.score), "domain": domain, **dict(point.payload or {})}
                for point in response.points
            ]
        except Exception as exc:
            logger.warning("Qdrant search failed for %s; using memory fallback: %s", collection, exc)
            return self._memory_search(collection, vector, domain, top_k, filters or {})

    def _to_qdrant_filter(self, filters: dict[str, object]) -> Filter | None:
        if not Filter:
            return None
        conditions: list[FieldCondition] = []
        for key in ("cves", "domains", "ips", "mitre_techniques", "mitre_tactics", "rule_type", "log_source", "actor_names", "malware_families", "campaigns", "clusters", "relationship_tags", "tools", "phase", "tool_tags", "session_ids", "memory_types", "investigation_ids", "memory_tags", "paths", "path", "language", "vulnerability_types", "framework", "search_engine", "category", "tags"):
            values = filters.get(key)
            if isinstance(values, list) and values:
                conditions.append(FieldCondition(key=key, match=MatchAny(any=values)))
        return Filter(should=conditions) if conditions else None

    def _memory_search(self, collection: str, vector: list[float], domain: str, top_k: int, filters: dict[str, object] | None = None) -> list[dict[str, object]]:
        scored = []
        for point in _MEMORY_POINTS.get(collection, []):
            if not self._payload_matches(dict(point["payload"]), filters or {}):
                continue
            score = self.embedder.cosine(vector, point["vector"])
            scored.append({"score": score, "domain": domain, **dict(point["payload"])})
        return sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:top_k]

    def _payload_matches(self, payload: dict[str, object], filters: dict[str, object]) -> bool:
        for key, expected in filters.items():
            if not expected:
                continue
            expected_values = expected if isinstance(expected, list) else [expected]
            actual = payload.get(key)
            if isinstance(actual, list):
                if not any(value in actual for value in expected_values):
                    return False
            elif actual not in expected_values:
                return False
        return True

    def _load_fallback(self) -> None:
        if not _FALLBACK_PATH.exists():
            return
        try:
            data = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _MEMORY_POINTS.update(data)
        except Exception as exc:
            logger.warning("failed to load vector fallback store: %s", exc)

    def _save_fallback(self) -> None:
        try:
            _FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
            _FALLBACK_PATH.write_text(json.dumps(_MEMORY_POINTS), encoding="utf-8")
        except Exception as exc:
            logger.warning("failed to save vector fallback store: %s", exc)
