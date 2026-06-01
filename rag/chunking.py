"""Markdown-aware chunking helpers for RAG ingestion."""

from __future__ import annotations


def chunk_markdown(text: str, *, chunk_size: int = 1800, overlap: int = 250) -> list[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    sections = cleaned.split("\n## ")
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        start = 0
        while start < len(section):
            end = min(len(section), start + chunk_size)
            chunks.append(section[start:end].strip())
            if end >= len(section):
                break
            start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


__all__ = ["chunk_markdown"]

