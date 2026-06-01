import logging

from backend.rag.chunker import chunk_note
from backend.rag.qdrant_store import QdrantStore
from backend.vault.service import VaultService


logger = logging.getLogger("anubis.rag.indexer")


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
        logger.info("reindexed vault chunks=%s", len(chunks))
        return len(chunks)

    def index_note(self, note_path: str) -> int:
        content = self.vault.read_note(note_path)
        chunks = chunk_note(note_path, content)
        self.store.delete_path(note_path)
        self.store.upsert_chunks(chunks)
        logger.info("indexed note path=%s chunks=%s", note_path, len(chunks))
        return len(chunks)

    def delete_note(self, note_path: str) -> None:
        self.store.delete_path(note_path)
        logger.info("removed note vectors path=%s", note_path)
