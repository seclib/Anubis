import logging
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from backend.core.config import settings
from backend.rag.chunker import Chunk
from backend.rag.embedder import LocalEmbedder


logger = logging.getLogger("anubis.rag.qdrant")
_FALLBACK_POINTS: dict[str, dict[str, object]] = {}


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embedder = LocalEmbedder()
        self.collection = settings.qdrant_collection

    def ensure_collection(self) -> None:
        try:
            if self.client.collection_exists(self.collection):
                return
            logger.info("creating qdrant collection=%s dimensions=%s", self.collection, self.embedder.dimensions)
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
            )
        except Exception as exc:  # pragma: no cover - exercised when local qdrant is unavailable
            logger.warning("qdrant unavailable; using local search fallback: %s", exc)
            raise RuntimeError("qdrant unavailable") from exc

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        fallback_points = [
            {
                "id": str(uuid5(NAMESPACE_URL, chunk.id)),
                "vector": self.embedder.embed(chunk.text),
                "payload": chunk.__dict__,
            }
            for chunk in chunks
        ]
        for point in fallback_points:
            _FALLBACK_POINTS[str(point["id"])] = point
        points = [
            PointStruct(
                id=point["id"],
                vector=point["vector"],
                payload=point["payload"],
            )
            for point in fallback_points
        ]
        try:
            self.ensure_collection()
            if points:
                self.client.upsert(collection_name=self.collection, points=points)
            logger.info("upserted qdrant points=%s collection=%s", len(points), self.collection)
        except Exception as exc:  # pragma: no cover - qdrant state varies by environment
            logger.warning("qdrant upsert failed; using local search fallback: %s", exc)
            logger.info("upserted fallback points=%s", len(fallback_points))

    def delete_path(self, path: str) -> None:
        deleted = [point_id for point_id, point in _FALLBACK_POINTS.items() if point["payload"].get("path") == path]
        for point_id in deleted:
            _FALLBACK_POINTS.pop(point_id, None)
        try:
            self.ensure_collection()
            self.client.delete(
                collection_name=self.collection,
                points_selector=Filter(
                    must=[FieldCondition(key="path", match=MatchValue(value=path))]
                ),
            )
            logger.info("deleted qdrant path=%s fallback_points=%s", path, len(deleted))
        except Exception as exc:  # pragma: no cover - qdrant state varies by environment
            logger.warning("qdrant delete failed; using local search fallback: %s", exc)
            logger.info("deleted fallback path=%s points=%s", path, len(deleted))

    def search(self, query: str, limit: int) -> list[dict[str, object]]:
        vector = self.embedder.embed(query)
        try:
            self.ensure_collection()
            response = self.client.query_points(
                collection_name=self.collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            results = [{"score": result.score, **dict(result.payload or {})} for result in response.points]
            logger.info("qdrant query collection=%s limit=%s results=%s", self.collection, limit, len(results))
            return results
        except Exception as exc:  # pragma: no cover - qdrant state varies by environment
            logger.warning("qdrant query failed; using local search fallback: %s", exc)
            scored = [
                {"score": _cosine(vector, point["vector"]), **dict(point["payload"])}
                for point in _FALLBACK_POINTS.values()
            ]
            results = sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:limit]
            logger.info("fallback query limit=%s results=%s", limit, len(results))
            return results
