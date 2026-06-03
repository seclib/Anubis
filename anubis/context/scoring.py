from __future__ import annotations

from anubis.context.embeddings import tokenize
from anubis.context.schema import CodeChunk, FileMetadata


class ContextScorer:
    def __init__(self, files: tuple[FileMetadata, ...]) -> None:
        self.files = {file.path: file for file in files}
        self.max_size = max((file.size_bytes for file in files), default=1)
        self.max_mtime = max((file.mtime_ns for file in files), default=1)

    def score(
        self,
        *,
        task: str,
        chunk: CodeChunk,
        semantic_score: float,
        expanded_terms: set[str],
    ) -> tuple[float, float, float, float]:
        keyword_score = self.keyword_score(chunk, expanded_terms)
        file_importance = self.file_importance(chunk)
        symbol_score = self.symbol_relevance(chunk, expanded_terms)
        total = (
            semantic_score * 0.45
            + keyword_score * 0.25
            + symbol_score * 0.20
            + file_importance * 0.10
        )
        return round(total, 6), round(keyword_score, 6), round(file_importance, 6), round(symbol_score, 6)

    def keyword_score(self, chunk: CodeChunk, terms: set[str]) -> float:
        haystack = set(tokenize(f"{chunk.file_path}\n{chunk.content}"))
        if not terms:
            return 0.0
        return len(terms & haystack) / len(terms)

    def file_importance(self, chunk: CodeChunk) -> float:
        file = self.files.get(chunk.file_path)
        if file is None:
            return 0.0
        recency = file.mtime_ns / self.max_mtime if self.max_mtime else 0.0
        size_signal = min(1.0, file.size_bytes / max(1, self.max_size))
        return recency * 0.7 + size_signal * 0.3

    def symbol_relevance(self, chunk: CodeChunk, terms: set[str]) -> float:
        symbols = {symbol.lower() for symbol in chunk.symbols}
        if not terms or not symbols:
            return 0.0
        direct = len(terms & symbols)
        partial = sum(1 for term in terms for symbol in symbols if term in symbol or symbol in term)
        return min(1.0, (direct + partial * 0.5) / max(1, len(terms)))


__all__ = ["ContextScorer"]
