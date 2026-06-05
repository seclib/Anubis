from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import blake2b, sha256
import math
from pathlib import Path
import re
from typing import Iterable


DEFAULT_CHUNK_CHARS = 1400
DEFAULT_CHUNK_OVERLAP = 180
DEFAULT_EMBEDDING_DIMENSIONS = 256


@dataclass(frozen=True)
class ObsidianNote:
    path: str
    title: str
    content: str
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ObsidianChunk:
    id: str
    note_path: str
    title: str
    heading: str
    text: str
    line_start: int
    line_end: int
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    hash: str = ""


@dataclass(frozen=True)
class RetrievalResult:
    score: float
    chunk: ObsidianChunk

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self.chunk)
        payload["score"] = self.score
        payload["path"] = self.chunk.note_path
        return payload


class ObsidianVaultScanner:
    def __init__(self, vault_path: str | Path, *, ignored_dirs: Iterable[str] | None = None) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.ignored_dirs = set(ignored_dirs or {".obsidian", ".git", "__pycache__", ".trash"})

    def scan(self) -> list[ObsidianNote]:
        if not self.vault_path.exists():
            return []
        notes: list[ObsidianNote] = []
        for path in sorted(self.vault_path.rglob("*.md")):
            if self._ignored(path):
                continue
            rel = path.relative_to(self.vault_path).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            metadata, body = parse_frontmatter(content)
            tags = extract_tags(content, metadata)
            title = metadata.get("title") or first_heading(body) or path.stem
            notes.append(ObsidianNote(path=rel, title=title, content=body, tags=tags, metadata=metadata))
        return notes

    def _ignored(self, path: Path) -> bool:
        try:
            rel_parts = path.relative_to(self.vault_path).parts
        except ValueError:
            return True
        return any(part in self.ignored_dirs for part in rel_parts)


class MarkdownChunker:
    def __init__(self, *, chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_CHUNK_OVERLAP) -> None:
        if chunk_chars < 200:
            raise ValueError("chunk_chars must be at least 200")
        if overlap < 0 or overlap >= chunk_chars:
            raise ValueError("overlap must be non-negative and smaller than chunk_chars")
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def chunk(self, note: ObsidianNote) -> list[ObsidianChunk]:
        chunks: list[ObsidianChunk] = []
        for section_index, section in enumerate(markdown_sections(note.content)):
            for part_index, part in enumerate(self._split_section(section["text"])):
                text = part.strip()
                if not text:
                    continue
                digest = sha256(f"{note.path}\n{section['heading']}\n{text}".encode("utf-8")).hexdigest()
                chunks.append(
                    ObsidianChunk(
                        id=f"{note.path}::section-{section_index}::chunk-{part_index}",
                        note_path=note.path,
                        title=note.title,
                        heading=str(section["heading"]),
                        text=text,
                        line_start=int(section["line_start"]),
                        line_end=int(section["line_end"]),
                        tags=note.tags,
                        metadata=note.metadata,
                        hash=digest,
                    )
                )
        return chunks

    def _split_section(self, text: str) -> list[str]:
        if len(text) <= self.chunk_chars:
            return [text]
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph.strip()
            if len(candidate) <= self.chunk_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(paragraph) <= self.chunk_chars:
                current = paragraph.strip()
            else:
                chunks.extend(self._split_long_text(paragraph))
                current = ""
        if current:
            chunks.append(current)
        return with_overlap(chunks, self.overlap)

    def _split_long_text(self, text: str) -> list[str]:
        parts = []
        step = self.chunk_chars - self.overlap
        for start in range(0, len(text), step):
            part = text[start : start + self.chunk_chars].strip()
            if part:
                parts.append(part)
        return parts


class HashEmbeddingPipeline:
    """Deterministic local embedding pipeline with no model server requirement."""

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be at least 16")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [value / norm for value in vector]

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class InMemoryVectorIndex:
    def __init__(self, embedder: HashEmbeddingPipeline | None = None) -> None:
        self.embedder = embedder or HashEmbeddingPipeline()
        self._rows: list[tuple[ObsidianChunk, list[float]]] = []

    @property
    def size(self) -> int:
        return len(self._rows)

    def clear(self) -> None:
        self._rows.clear()

    def upsert(self, chunks: Iterable[ObsidianChunk]) -> int:
        incoming = list(chunks)
        incoming_ids = {chunk.id for chunk in incoming}
        self._rows = [(chunk, vector) for chunk, vector in self._rows if chunk.id not in incoming_ids]
        vectors = self.embedder.embed_many(chunk.text for chunk in incoming)
        self._rows.extend(zip(incoming, vectors, strict=True))
        return len(incoming)

    def search(self, query: str, *, limit: int = 6, tags: Iterable[str] | None = None) -> list[RetrievalResult]:
        query_vector = self.embedder.embed(query)
        required_tags = {tag.lower().lstrip("#") for tag in tags or []}
        scored: list[RetrievalResult] = []
        for chunk, vector in self._rows:
            if required_tags and not required_tags <= {tag.lower().lstrip("#") for tag in chunk.tags}:
                continue
            scored.append(RetrievalResult(score=cosine(query_vector, vector), chunk=chunk))
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:limit]


class ObsidianMemoryRag:
    def __init__(
        self,
        vault_path: str | Path,
        *,
        scanner: ObsidianVaultScanner | None = None,
        chunker: MarkdownChunker | None = None,
        embedder: HashEmbeddingPipeline | None = None,
        index: InMemoryVectorIndex | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.scanner = scanner or ObsidianVaultScanner(self.vault_path)
        self.chunker = chunker or MarkdownChunker()
        self.embedder = embedder or HashEmbeddingPipeline()
        self.index = index or InMemoryVectorIndex(self.embedder)

    def ingest(self) -> dict[str, int]:
        notes = self.scanner.scan()
        chunks = [chunk for note in notes for chunk in self.chunker.chunk(note)]
        self.index.clear()
        self.index.upsert(chunks)
        return {"notes": len(notes), "chunks": len(chunks), "vectors": self.index.size}

    def retrieve(self, query: str, *, limit: int = 6, tags: Iterable[str] | None = None) -> list[dict[str, object]]:
        return [result.to_dict() for result in self.index.search(query, limit=limit, tags=tags)]


def ingest_obsidian_vault(vault_path: str | Path) -> ObsidianMemoryRag:
    rag = ObsidianMemoryRag(vault_path)
    rag.ingest()
    return rag


def retrieve_from_obsidian(
    vault_path: str | Path,
    query: str,
    *,
    limit: int = 6,
    tags: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    rag = ingest_obsidian_vault(vault_path)
    return rag.retrieve(query, limit=limit, tags=tags)


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---", 4)
    if end < 0:
        return {}, content
    raw = content[4:end].strip()
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, content[end + 4 :].lstrip("\n")


def extract_tags(content: str, metadata: dict[str, str]) -> tuple[str, ...]:
    tags: set[str] = set()
    raw_tags = metadata.get("tags", "")
    for item in re.split(r"[\s,\[\]]+", raw_tags):
        cleaned = item.strip().strip('"').strip("'").lstrip("#")
        if cleaned:
            tags.add(cleaned)
    for match in re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", content):
        tags.add(match)
    return tuple(sorted(tags))


def first_heading(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def markdown_sections(content: str) -> list[dict[str, object]]:
    lines = content.splitlines()
    sections: list[dict[str, object]] = []
    heading = "Document"
    start = 1
    buffer: list[str] = []
    in_code = False
    for line_number, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
        is_heading = not in_code and bool(re.match(r"^#{1,4}\s+", line))
        if is_heading:
            if buffer:
                sections.append({"heading": heading, "text": "\n".join(buffer).strip(), "line_start": start, "line_end": line_number - 1})
            heading = line.lstrip("#").strip()
            start = line_number
            buffer = [line]
            continue
        buffer.append(line)
    if buffer:
        sections.append({"heading": heading, "text": "\n".join(buffer).strip(), "line_start": start, "line_end": len(lines)})
    return [section for section in sections if str(section["text"]).strip()]


def with_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:]):
        prefix = previous[-overlap:].strip()
        result.append(f"{prefix}\n\n{current}".strip() if prefix else current)
    return result


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_/-]{1,}", text.lower())


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
