from __future__ import annotations

from anubis.context.embeddings import tokenize
from anubis.context.schema import RetrievedContext


class ContextCompressor:
    def __init__(self, max_chars: int = 8000, per_chunk_chars: int = 1600) -> None:
        self.max_chars = max_chars
        self.per_chunk_chars = per_chunk_chars

    def compress(self, task: str, contexts: tuple[RetrievedContext, ...]) -> tuple[list[dict[str, object]], str]:
        seen: set[tuple[str, int, int]] = set()
        chunks: list[dict[str, object]] = []
        summary_lines: list[str] = []
        used = 0
        task_terms = set(tokenize(task))
        for item in contexts:
            key = (item.chunk.file_path, item.chunk.start_line, item.chunk.end_line)
            if key in seen:
                continue
            seen.add(key)
            content = self._trim(item.chunk.content, task_terms)
            if used + len(content) > self.max_chars:
                break
            chunks.append(
                {
                    "file": item.chunk.file_path,
                    "content": content,
                    "score": item.score,
                    "metadata": {
                        "language": item.chunk.language,
                        "symbols": list(item.chunk.symbols),
                        "start_line": item.chunk.start_line,
                        "end_line": item.chunk.end_line,
                        "semantic_score": item.semantic_score,
                        "keyword_score": item.keyword_score,
                        "file_importance": item.file_importance,
                        "symbol_score": item.symbol_score,
                    },
                }
            )
            summary_lines.append(
                f"{item.chunk.file_path}:{item.chunk.start_line}-{item.chunk.end_line} "
                f"symbols={','.join(item.chunk.symbols) or 'none'} score={item.score}"
            )
            used += len(content)
        return chunks, "\n".join(summary_lines)

    def _trim(self, content: str, task_terms: set[str]) -> str:
        lines = content.splitlines()
        if len(content) <= self.per_chunk_chars:
            return content
        scored_lines = []
        for index, line in enumerate(lines):
            score = len(task_terms & set(tokenize(line)))
            scored_lines.append((score, index, line))
        selected = sorted(scored_lines, key=lambda item: (-item[0], item[1]))[:40]
        selected_indexes = sorted(index for _, index, _ in selected)
        trimmed = "\n".join(lines[index] for index in selected_indexes)
        return trimmed[: self.per_chunk_chars]


__all__ = ["ContextCompressor"]
