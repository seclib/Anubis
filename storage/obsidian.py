"""Obsidian vault storage adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge.ingestion import get_obsidian_ingestion_pipeline
from memory import hermes


class ObsidianStore:
    def root(self) -> Path:
        return hermes.obsidian_vault_path(create=True)

    def health(self) -> dict[str, Any]:
        try:
            root = self.root()
            return {"ok": root.exists() and root.is_dir(), "path": str(root)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def write_note(self, title: str, content: str, folder: str = "Inbox") -> dict[str, Any]:
        return hermes.write_obsidian_note(title=title, content=content, folder=folder)

    def index(self, force: bool = False) -> dict[str, Any]:
        return hermes.index_obsidian_vault(force=force)

    def ingest(self, *, limit: int | None = None, force: bool = False, index_qdrant: bool = True) -> dict[str, Any]:
        return get_obsidian_ingestion_pipeline().ingest_vault(
            limit=limit,
            force=force,
            index_qdrant=index_qdrant,
        )

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return hermes.search_obsidian_notes(query=query, top_k=top_k)


__all__ = ["ObsidianStore"]
