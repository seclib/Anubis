from backend.rag.chunker import chunk_note
from backend.rag.qdrant_store import QdrantStore
from backend.vault.service import VaultService


class RagIndexer:
    def __init__(self) -> None:
        self.vault = VaultService()
        self.store = QdrantStore()

    def reindex_all(self) -> int:
        chunks = []
        for note in self.vault.list_notes():
            content = self.vault.read_note(note["path"])
            chunks.extend(chunk_note(note["path"], content))
        self.store.upsert_chunks(chunks)
        return len(chunks)
