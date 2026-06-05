from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SEARCH_ENGINES = ("google", "github", "gitlab", "shodan", "censys", "fofa")


@dataclass(frozen=True)
class DiscoveryEntry:
    title: str
    source: str
    category: str
    query: str
    description: str = ""
    tags: tuple[str, ...] = ()
    search_engine: str = ""
    source_uri: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        return stable_id("discovery", self.source, self.category, self.query)

    def searchable_text(self) -> str:
        return "\n".join(
            part
            for part in (
                self.title,
                self.source,
                self.category,
                self.search_engine,
                self.query,
                self.description,
                " ".join(self.tags),
            )
            if part
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryEntry:
        return cls(
            title=str(data.get("title") or ""),
            source=str(data.get("source") or ""),
            category=str(data.get("category") or ""),
            query=str(data.get("query") or ""),
            description=str(data.get("description") or ""),
            tags=tuple(data.get("tags") or ()),
            search_engine=str(data.get("search_engine") or ""),
            source_uri=str(data.get("source_uri") or ""),
            raw=dict(data.get("raw") or {}),
        )


@dataclass(frozen=True)
class DiscoveryChunk:
    chunk_id: str
    doc_id: str
    text: str
    title: str
    source_uri: str
    metadata: dict[str, Any]
    domain: str = "discovery"

    def to_vector_chunk(self) -> VectorChunkAdapter:
        return VectorChunkAdapter(
            chunk_id=self.chunk_id,
            doc_id=self.doc_id,
            domain=self.domain,
            text=self.text,
            source_uri=self.source_uri,
            title=self.title,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class VectorChunkAdapter:
    chunk_id: str
    doc_id: str
    domain: str
    text: str
    source_uri: str
    title: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DiscoverySearchResult:
    entry: DiscoveryEntry
    score: float
    keyword_score: float
    semantic_score: float
    matched_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "keyword_score": self.keyword_score,
            "semantic_score": self.semantic_score,
            "matched_terms": list(self.matched_terms),
            "entry": self.entry.to_dict(),
        }

    def cli_summary(self) -> str:
        tags = ", ".join(self.entry.tags) if self.entry.tags else "none"
        return (
            f"[{self.score:.3f}] {self.entry.title}\n"
            f"  engine={self.entry.search_engine or 'unknown'} category={self.entry.category or 'uncategorized'} "
            f"source={self.entry.source or 'unknown'} tags={tags}\n"
            f"  query={self.entry.query}"
        )


def stable_id(*parts: object) -> str:
    payload = "::".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
