"""Local-first markdown vault workspace for ANUBIS desktop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

from anubis.memory import MemoryCollection, UnifiedMemoryService


class VaultWorkspaceError(RuntimeError):
    """Raised when a vault operation cannot be completed safely."""


@dataclass(frozen=True)
class VaultNote:
    path: str
    title: str
    preview: str
    tags: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    updated_at: float = 0.0
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "tags": list(self.tags),
            "links": list(self.links),
        }


@dataclass(frozen=True)
class VaultBacklink:
    source_path: str
    title: str
    excerpt: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VaultGraphNode:
    id: str
    path: str
    title: str
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "tags": list(self.tags)}


@dataclass(frozen=True)
class VaultGraphEdge:
    source: str
    target: str
    type: str = "links_to"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VaultGraph:
    nodes: tuple[VaultGraphNode, ...] = ()
    edges: tuple[VaultGraphEdge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True)
class VaultSearchResult:
    path: str
    title: str
    score: float
    excerpt: str
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VaultWriteResult:
    path: str
    indexed: bool
    inserted: int = 0
    deduplicated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VaultWorkspaceSnapshot:
    notes: tuple[VaultNote, ...] = ()
    graph: VaultGraph = field(default_factory=VaultGraph)

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes": [note.to_dict() for note in self.notes],
            "graph": self.graph.to_dict(),
        }


class VaultWorkspace:
    """Obsidian-inspired navigation, backlinks, graph, and memory search."""

    def __init__(self, root: str | Path, *, memory: UnifiedMemoryService | None = None) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory = memory or UnifiedMemoryService()

    def snapshot(self) -> VaultWorkspaceSnapshot:
        notes = self.list_notes()
        return VaultWorkspaceSnapshot(notes=notes, graph=self.graph(notes=notes))

    def list_notes(self) -> tuple[VaultNote, ...]:
        notes = [self._note_from_path(path) for path in self.root.rglob("*.md") if path.is_file()]
        notes.sort(key=lambda note: (-note.updated_at, note.path.lower()))
        return tuple(notes)

    def read_note(self, note_path: str | Path) -> str:
        path = self._resolve(note_path)
        if path.suffix.lower() != ".md":
            raise VaultWorkspaceError("Only markdown notes can be read")
        if not path.exists():
            raise VaultWorkspaceError(f"Note not found: {self._relative(path)}")
        return path.read_text(encoding="utf-8")

    def write_note(self, note_path: str | Path, content: str, *, index: bool = True) -> VaultWriteResult:
        path = self._resolve(note_path)
        if path.suffix.lower() != ".md":
            raise VaultWorkspaceError("Only markdown notes can be written")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")
        inserted = deduplicated = 0
        if index:
            result = self.index_note(path)
            inserted = result.inserted
            deduplicated = result.deduplicated
        return VaultWriteResult(path=self._relative(path), indexed=index, inserted=inserted, deduplicated=deduplicated)

    def backlinks(self, note_path: str | Path) -> tuple[VaultBacklink, ...]:
        target = self._resolve(note_path)
        target_note = self._note_from_path(target) if target.exists() else None
        target_keys = self._target_keys(target, title=target_note.title if target_note else None)
        results: list[VaultBacklink] = []
        for source in self.root.rglob("*.md"):
            if source.resolve() == target:
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            links = _extract_links(text)
            if not any(self._link_matches(link, target_keys) for link in links):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(link in line for link in links if self._link_matches(link, target_keys)):
                    note = self._note_from_path(source)
                    results.append(
                        VaultBacklink(
                            source_path=note.path,
                            title=note.title,
                            excerpt=_clean_preview(line, limit=180),
                            line=line_number,
                        )
                    )
                    break
        results.sort(key=lambda item: (item.source_path.lower(), item.line))
        return tuple(results)

    def graph(self, *, notes: tuple[VaultNote, ...] | None = None) -> VaultGraph:
        all_notes = notes or self.list_notes()
        resolver = self._resolver(all_notes)
        nodes = tuple(VaultGraphNode(id=note.path, path=note.path, title=note.title, tags=note.tags) for note in all_notes)
        edges: set[tuple[str, str]] = set()
        for note in all_notes:
            for link in note.links:
                target = resolver.get(_normalize_link_key(link))
                if target and target != note.path:
                    edges.add((note.path, target))
        graph_edges = tuple(
            VaultGraphEdge(source=source, target=target)
            for source, target in sorted(edges, key=lambda edge: (edge[0].lower(), edge[1].lower()))
        )
        return VaultGraph(nodes=nodes, edges=graph_edges)

    def search(self, query: str, *, limit: int = 8) -> tuple[VaultSearchResult, ...]:
        normalized = " ".join(str(query).lower().split())
        if not normalized:
            return ()
        results: dict[str, VaultSearchResult] = {}
        for note in self.list_notes():
            text = self.read_note(note.path)
            score = _lexical_score(normalized, note, text)
            if score <= 0:
                continue
            results[note.path] = VaultSearchResult(
                path=note.path,
                title=note.title,
                score=score,
                excerpt=_best_excerpt(text, normalized),
                source="local",
            )
        for memory_result in self.memory.retrieve(normalized, collections=(MemoryCollection.DOCS,), limit=limit, min_score=0.0):
            record = memory_result.record
            path = str(record.metadata.get("path") or record.source)
            if not path.endswith(".md"):
                continue
            existing = results.get(path)
            score = min(1.0, max(0.0, float(memory_result.score))) + 0.15
            if existing and existing.score >= score:
                continue
            results[path] = VaultSearchResult(
                path=path,
                title=str(record.metadata.get("title") or Path(path).stem),
                score=score,
                excerpt=_best_excerpt(record.text, normalized),
                source="memory",
            )
        ranked = sorted(results.values(), key=lambda item: (-item.score, item.path.lower()))
        return tuple(ranked[: max(1, int(limit))])

    def index_note(self, note_path: str | Path):
        path = self._resolve(note_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        note = self._note_from_path(path)
        return self.memory.remember(
            MemoryCollection.DOCS,
            text,
            source=note.path,
            metadata={
                "path": note.path,
                "title": note.title,
                "tags": list(note.tags),
                "links": list(note.links),
                "kind": "vault_note",
            },
            record_id=f"vault:{note.path}",
        )

    def index_all(self):
        inserted = deduplicated = 0
        ids: list[str] = []
        for note in self.list_notes():
            result = self.index_note(note.path)
            inserted += result.inserted
            deduplicated += result.deduplicated
            ids.extend(result.ids)
        return {"inserted": inserted, "deduplicated": deduplicated, "ids": ids}

    def _note_from_path(self, path: Path) -> VaultNote:
        resolved = self._resolve(path)
        text = resolved.read_text(encoding="utf-8", errors="replace")
        stat = resolved.stat()
        return VaultNote(
            path=self._relative(resolved),
            title=_title_from_markdown(text, fallback=resolved.stem),
            preview=_clean_preview(text),
            tags=tuple(sorted(set(_extract_tags(text)))),
            links=tuple(dict.fromkeys(_extract_links(text))),
            updated_at=stat.st_mtime,
            size_bytes=stat.st_size,
        )

    def _resolve(self, candidate: str | Path) -> Path:
        path = Path(candidate)
        resolved = path.resolve() if path.is_absolute() else (self.root / path).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise VaultWorkspaceError("Path escapes the vault")
        return resolved

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _resolver(self, notes: tuple[VaultNote, ...]) -> dict[str, str]:
        resolver: dict[str, str] = {}
        for note in notes:
            variants = {
                note.path,
                note.path.removesuffix(".md"),
                Path(note.path).stem,
                note.title,
            }
            for variant in variants:
                resolver[_normalize_link_key(variant)] = note.path
        return resolver

    def _target_keys(self, target: Path, *, title: str | None) -> set[str]:
        relative = self._relative(target)
        return {
            _normalize_link_key(relative),
            _normalize_link_key(relative.removesuffix(".md")),
            _normalize_link_key(target.stem),
            _normalize_link_key(title or target.stem),
        }

    def _link_matches(self, link: str, target_keys: set[str]) -> bool:
        return _normalize_link_key(link) in target_keys


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+(?:\.md)?)\)")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")


def _title_from_markdown(markdown: str, *, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback.replace("_", " ").replace("-", " ").strip().title() or "Untitled"


def _extract_links(markdown: str) -> list[str]:
    links: list[str] = []
    links.extend(match.group(1).strip() for match in WIKILINK_RE.finditer(markdown))
    for match in MARKDOWN_LINK_RE.finditer(markdown):
        target = match.group(1).strip()
        if target.endswith(".md"):
            links.append(target)
    return [link for link in links if link]


def _extract_tags(markdown: str) -> list[str]:
    return [match.group(1).strip("/") for match in TAG_RE.finditer(markdown)]


def _clean_preview(markdown: str, *, limit: int = 220) -> str:
    plain = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    plain = re.sub(r"^#+\s*", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda match: match.group(2) or match.group(1), plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    plain = re.sub(r"[*_`>-]", " ", plain)
    plain = " ".join(plain.split())
    return plain[:limit].strip()


def _normalize_link_key(value: str) -> str:
    key = value.strip().replace("\\", "/")
    key = key.removesuffix(".md")
    return " ".join(key.lower().split())


def _lexical_score(query: str, note: VaultNote, text: str) -> float:
    haystack = f"{note.title} {' '.join(note.tags)} {text}".lower()
    terms = query.split()
    if query in haystack:
        return min(1.0, 0.55 + (0.08 * len(terms)))
    matches = sum(1 for term in terms if term in haystack)
    if matches == 0:
        return 0.0
    return min(0.9, matches / max(1, len(terms)) * 0.7)


def _best_excerpt(text: str, query: str) -> str:
    cleaned_lines = [_clean_preview(line, limit=180) for line in text.splitlines()]
    for line in cleaned_lines:
        if query in line.lower():
            return line
    terms = query.split()
    for line in cleaned_lines:
        lower = line.lower()
        if any(term in lower for term in terms):
            return line
    return _clean_preview(text, limit=180)


__all__ = [
    "VaultBacklink",
    "VaultGraph",
    "VaultGraphEdge",
    "VaultGraphNode",
    "VaultNote",
    "VaultSearchResult",
    "VaultWorkspace",
    "VaultWorkspaceError",
    "VaultWorkspaceSnapshot",
    "VaultWriteResult",
]
