"""Retriever facade for code that wants RAG-specific imports."""

from __future__ import annotations

from typing import Any

from rag.service import get_rag_service


def retrieve(query: str, top_k: int = 8, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_rag_service().query(query, top_k=top_k, filters=filters or {})


__all__ = ["retrieve"]

