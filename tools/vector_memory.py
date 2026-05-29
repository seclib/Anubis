"""Tool wrappers for local vector memory."""

from __future__ import annotations

from memory.vector import (
    index_repository as _index_repository,
    retrieve_context as _retrieve_context,
    semantic_search as _semantic_search,
)


def index_repository(root: str = ".", force: bool = False) -> dict:
    return _index_repository(root=root, force=force)


def semantic_search(query: str, top_k: int = 5, kind: str | None = None) -> list[dict]:
    return _semantic_search(query=query, top_k=top_k, kind=kind)


def retrieve_context(query: str, top_k: int = 5) -> str:
    return _retrieve_context(query=query, top_k=top_k)


__all__ = ["index_repository", "retrieve_context", "semantic_search"]
