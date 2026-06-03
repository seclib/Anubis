from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from backend.context.retriever import RetrievedChunk


@dataclass(frozen=True)
class CompressedContext:
    task: str
    text: str
    chunks: list[dict[str, object]]
    token_budget_chars: int


class ContextCompressor:
    def __init__(self, max_chars: int = 7000, per_chunk_chars: int = 1200) -> None:
        self.max_chars = max_chars
        self.per_chunk_chars = per_chunk_chars

    def compress(self, task: str, chunks: list[RetrievedChunk]) -> CompressedContext:
        task_terms = set(_terms(task))
        blocks: list[str] = []
        used = 0
        compressed_chunks: list[dict[str, object]] = []

        for index, chunk in enumerate(chunks, start=1):
            snippet = self._snippet(chunk.text, task_terms)
            block = (
                f"[{index}] {chunk.path}:{chunk.start}-{chunk.end} "
                f"score={chunk.score}\n{snippet}"
            )
            if used + len(block) > self.max_chars:
                break
            blocks.append(block)
            used += len(block) + 2
            compressed_chunks.append(
                {
                    **asdict(chunk),
                    "text": snippet,
                }
            )

        return CompressedContext(
            task=task,
            text="\n\n".join(blocks),
            chunks=compressed_chunks,
            token_budget_chars=self.max_chars,
        )

    def _snippet(self, text: str, task_terms: set[str]) -> str:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            return text[: self.per_chunk_chars]
        ranked = sorted(
            paragraphs,
            key=lambda paragraph: len(task_terms & set(_terms(paragraph))),
            reverse=True,
        )
        snippet = "\n\n".join(ranked[:3])
        return snippet[: self.per_chunk_chars].strip()


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_/-]{2,}", text.lower())


__all__ = ["CompressedContext", "ContextCompressor"]
