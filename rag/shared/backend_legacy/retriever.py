import logging

from rag.shared.backend_legacy.qdrant_store import QdrantStore


logger = logging.getLogger("anubis.rag.retriever")


class RagRetriever:
    def __init__(self) -> None:
        self.store = QdrantStore()

    def search(self, query: str, limit: int = 6) -> list[dict[str, object]]:
        results = self.store.search(query, limit)
        logger.info("rag search chars=%s limit=%s results=%s", len(query), limit, len(results))
        return results
