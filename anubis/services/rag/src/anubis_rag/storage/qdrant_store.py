from __future__ import annotations

import hashlib
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from anubis_rag.core.config import Settings
from anubis_rag.models.documents import Chunk, RagSource, RetrievedChunk


class QdrantVectorStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncQdrantClient(url=str(settings.qdrant_url))

    async def ensure_collection(self) -> None:
        collections = await self._client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self._settings.qdrant_collection not in names:
            await self._client.create_collection(
                collection_name=self._settings.qdrant_collection,
                vectors_config=VectorParams(size=self._settings.embedding_dimensions, distance=Distance.COSINE),
            )

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=str(_point_uuid(chunk.id)),
                vector=vector,
                payload={
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "title": chunk.title,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            await self._client.upsert(collection_name=self._settings.qdrant_collection, points=points)

    async def search(self, vector: list[float], limit: int) -> list[RagSource]:
        chunks = await self.search_chunks(vector, limit)
        return [
            RagSource(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                score=chunk.relevance_score,
                excerpt=chunk.text[:500],
            )
            for chunk in chunks
        ]

    async def search_chunks(self, vector: list[float], limit: int) -> list[RetrievedChunk]:
        results = await self._client.search(
            collection_name=self._settings.qdrant_collection,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        chunks: list[RetrievedChunk] = []
        for result in results:
            payload = result.payload or {}
            text = str(payload.get("text", ""))
            metadata = payload.get("metadata", {})
            chunks.append(
                RetrievedChunk(
                    document_id=str(payload.get("document_id", "")),
                    chunk_id=str(payload.get("chunk_id", result.id)),
                    title=str(payload.get("title", "Untitled")),
                    text=text,
                    relevance_score=max(0.0, min(1.0, float(result.score))),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return chunks

    async def close(self) -> None:
        await self._client.close()


def _point_uuid(value: str) -> UUID:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return UUID(bytes=digest[:16])
