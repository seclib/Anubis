"""Lightweight keyword retrieval over local vector documents and Obsidian notes."""

from __future__ import annotations

import re
from typing import Any

from memory import hermes, vector


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_.:-]{2,}", value.lower())}


class KeywordIndex:
    def search(self, query: str, top_k: int = 10, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        results: list[dict[str, Any]] = []
        for doc in vector.load_vector_store().get("documents", []):
            if not isinstance(doc, dict):
                continue
            text = str(doc.get("text") or "")
            source = str(doc.get("source") or "")
            score = self._score(query_tokens, f"{source}\n{text}")
            if score <= 0:
                continue
            metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            if not _passes_filters(metadata, filters or {}):
                continue
            results.append(
                {
                    "score": round(score, 6),
                    "backend": "keyword",
                    "source": source,
                    "text": text,
                    "payload": {**metadata, "kind": doc.get("kind"), "chunk_id": doc.get("id")},
                }
            )
        for note in hermes.search_obsidian_notes(query, top_k=top_k * 2):
            results.append({**note, "backend": "obsidian_keyword", "payload": {"kind": "obsidian_note"}})
        results.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return results[: max(1, min(int(top_k), 100))]

    def _score(self, query_tokens: set[str], text: str) -> float:
        text_tokens = _tokens(text)
        if not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens)
        phrase_boost = 0.15 if " ".join(sorted(query_tokens)) in text.lower() else 0.0
        return (overlap / max(1, len(query_tokens))) + phrase_boost


def _passes_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected in (None, "", [], {}):
            continue
        actual = metadata.get(key)
        if isinstance(expected, dict):
            if "gte" in expected and float(actual or 0.0) < float(expected["gte"]):
                return False
            if "lte" in expected and float(actual or 0.0) > float(expected["lte"]):
                return False
        elif isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual not in (expected, str(expected)):
            return False
    return True


__all__ = ["KeywordIndex"]
