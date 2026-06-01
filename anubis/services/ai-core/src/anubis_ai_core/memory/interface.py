from __future__ import annotations

from pathlib import Path
from typing import Any

from anubis_memory_sdk import StructuredMemory, StructuredMemoryStore

from anubis_ai_core.clients.rag import RagClient
from anubis_ai_core.models.agent import MemoryContextItem


class AgentMemoryInterface:
    def __init__(self, *, rag_client: RagClient, data_dir: Path) -> None:
        self._rag_client = rag_client
        self._structured_store = StructuredMemoryStore(data_dir)

    async def retrieve(self, query: str, request_id: str, limit: int = 5) -> list[MemoryContextItem]:
        sources = await self._rag_client.search(query, request_id=request_id, limit=limit)
        return [
            MemoryContextItem(
                source="qdrant",
                content=source.excerpt,
                score=source.score,
                metadata={
                    "document_id": source.document_id,
                    "chunk_id": source.chunk_id,
                    "title": source.title,
                },
            )
            for source in sources
        ]

    async def store(self, namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        memory = StructuredMemory(namespace=namespace, payload=payload)
        await self._structured_store.append(memory)
        return {"memory_id": memory.id, "namespace": namespace}
