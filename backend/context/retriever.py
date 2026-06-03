from __future__ import annotations

from dataclasses import dataclass
import heapq
import json
from pathlib import Path
from typing import Any, Iterable

from backend.context.indexer import DEFAULT_INDEX_PATH, RepositoryIndexer, embed_text, tokenize
from backend.core.config import settings
from backend.core.paths import ensure_inside


@dataclass(frozen=True)
class RetrievedChunk:
    path: str
    chunk_id: int
    start: int
    end: int
    text: str
    score: float
    metadata: dict[str, Any]


class ContextRetriever:
    def __init__(
        self,
        root: Path | None = None,
        index_path: Path | None = None,
        *,
        indexer: RepositoryIndexer | None = None,
    ) -> None:
        self.root = (root or settings.project_root).resolve()
        raw_index_path = index_path or DEFAULT_INDEX_PATH
        self.index_path = ensure_inside(self.root, raw_index_path)
        self.indexer = indexer or RepositoryIndexer(self.root, self.index_path)

    def retrieve(self, task: str, top_k: int = 8) -> list[RetrievedChunk]:
        self.indexer.ensure_index()
        if not self.index_path.exists():
            return []

        query_embedding = embed_text(task)
        query_terms = set(tokenize(task))
        heap: list[tuple[float, int, RetrievedChunk]] = []

        for row_number, row in enumerate(self._iter_rows()):
            score = self._score(row, query_embedding, query_terms)
            if score <= 0:
                continue
            chunk = RetrievedChunk(
                path=str(row.get("path", "")),
                chunk_id=int(row.get("chunk_id", 0)),
                start=int(row.get("start", 0)),
                end=int(row.get("end", 0)),
                text=str(row.get("text", "")),
                score=round(score, 6),
                metadata={
                    "mtime_ns": row.get("mtime_ns"),
                    "size": row.get("size"),
                },
            )
            item = (chunk.score, row_number, chunk)
            if len(heap) < top_k:
                heapq.heappush(heap, item)
            elif item[0] > heap[0][0]:
                heapq.heapreplace(heap, item)

        return [item[2] for item in sorted(heap, key=lambda value: value[0], reverse=True)]

    def _iter_rows(self) -> Iterable[dict[str, Any]]:
        with self.index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row

    def _score(self, row: dict[str, Any], query_embedding: list[float], query_terms: set[str]) -> float:
        embedding = row.get("embedding")
        if not isinstance(embedding, list):
            return 0.0
        vector = [float(value) for value in embedding]
        semantic = sum(left * right for left, right in zip(query_embedding, vector))

        path = str(row.get("path", "")).lower()
        text = str(row.get("text", ""))
        chunk_terms = set(tokenize(f"{path}\n{text}"))
        lexical = len(query_terms & chunk_terms) / max(1, len(query_terms))
        path_boost = 0.15 if any(term in path for term in query_terms) else 0.0
        return semantic * 0.65 + lexical * 0.30 + path_boost


__all__ = ["ContextRetriever", "RetrievedChunk"]
