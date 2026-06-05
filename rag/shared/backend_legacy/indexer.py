import logging
from pathlib import Path

from rag.shared.backend_legacy.chunker import chunk_note
from rag.shared.backend_legacy.qdrant_store import QdrantStore


logger = logging.getLogger("anubis.rag.indexer")


def _ensure_inside(root: Path, relative_path: Path) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"path escapes vault root: {relative_path}")
    return candidate


class VaultService:
    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = vault_path or Path("vault")
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[dict[str, str]]:
        notes = []
        for path in sorted(self.vault_path.rglob("*.md")):
            rel = path.relative_to(self.vault_path).as_posix()
            notes.append({"path": rel, "title": path.stem})
        return notes

    def read_note(self, note_path: str) -> str:
        path = _ensure_inside(self.vault_path, Path(note_path))
        return path.read_text(encoding="utf-8")


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
