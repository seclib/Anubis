from backend.rag.qdrant_store import QdrantStore


class RagRetriever:
    def __init__(self) -> None:
        self.store = QdrantStore()

    def search(self, query: str, limit: int = 6) -> list[dict[str, object]]:
        return self.store.search(query, limit)
