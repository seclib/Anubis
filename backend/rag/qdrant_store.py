import logging
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.core.config import settings
from backend.rag.chunker import Chunk
from backend.rag.embedder import LocalEmbedder


logger = logging.getLogger("anubis.rag.qdrant")


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embedder = LocalEmbedder()
        self.collection = settings.qdrant_collection

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        logger.info("creating qdrant collection=%s dimensions=%s", self.collection, self.embedder.dimensions)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
        )

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        self.ensure_collection()
        points = [
            PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk.id)),
                vector=self.embedder.embed(chunk.text),
                payload=chunk.__dict__,
            )
            for chunk in chunks
        ]
        if points:
            self.client.upsert(collection_name=self.collection, points=points)
        logger.info("upserted qdrant points=%s collection=%s", len(points), self.collection)

    def search(self, query: str, limit: int) -> list[dict[str, object]]:
        self.ensure_collection()
        response = self.client.query_points(
            collection_name=self.collection,
            query=self.embedder.embed(query),
            limit=limit,
            with_payload=True,
        )
        results = [{"score": result.score, **dict(result.payload or {})} for result in response.points]
        logger.info("qdrant query collection=%s limit=%s results=%s", self.collection, limit, len(results))
        return results
