from __future__ import annotations

import re

from anubis_rag.models.documents import Chunk, DocumentInput


class MarkdownChunker:
    def __init__(self, chunk_size: int, overlap: int) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, document: DocumentInput) -> list[Chunk]:
        normalized = self._normalize_markdown(document.content)
        chunks: list[Chunk] = []
        start = 0
        index = 0
        while start < len(normalized):
            end = min(start + self._chunk_size, len(normalized))
            text = normalized[start:end].strip()
            if text:
                chunks.append(
                    Chunk(
                        id=f"{document.id}:{index}",
                        document_id=document.id,
                        title=document.title,
                        text=text,
                        metadata=document.metadata | {"source_type": document.source_type},
                    )
                )
            if end == len(normalized):
                break
            start = max(0, end - self._overlap)
            index += 1
        return chunks

    def _normalize_markdown(self, content: str) -> str:
        without_code_fence_noise = re.sub(r"```+", "```", content)
        return re.sub(r"\n{3,}", "\n\n", without_code_fence_noise).strip()
