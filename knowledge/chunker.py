"""Chunk Obsidian parsed notes for vector indexing."""

from __future__ import annotations

from dataclasses import dataclass

from knowledge.markdown_parser import ParsedNote
from memory import vector


@dataclass(frozen=True)
class NoteChunk:
    chunk_id: str
    document_id: str
    parent_id: str
    title: str
    heading_path: list[str]
    text: str
    chunk_index: int


class ObsidianChunker:
    def __init__(self, chunk_size: int = 1800, overlap: int = 250) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, parsed: ParsedNote) -> list[NoteChunk]:
        sections = self._sections(parsed)
        chunks: list[NoteChunk] = []
        document_id = f"obsidian:{parsed.note.relative_path}"
        for section_index, (heading_path, section_text) in enumerate(sections):
            parent_id = f"{document_id}:p{section_index}"
            start = 0
            local_index = 0
            while start < len(section_text):
                end = min(len(section_text), start + self.chunk_size)
                text = section_text[start:end].strip()
                if text:
                    digest = vector._content_hash(f"{parsed.note.content_hash}:{section_index}:{local_index}:{text}")[:16]
                    chunks.append(
                        NoteChunk(
                            chunk_id=f"{document_id}:c{section_index}:{local_index}:{digest}",
                            document_id=document_id,
                            parent_id=parent_id,
                            title=parsed.title,
                            heading_path=heading_path,
                            text=text,
                            chunk_index=len(chunks),
                        )
                    )
                if end >= len(section_text):
                    break
                start = max(0, end - self.overlap)
                local_index += 1
        return chunks

    def _sections(self, parsed: ParsedNote) -> list[tuple[list[str], str]]:
        lines = parsed.body.splitlines()
        sections: list[tuple[list[str], list[str]]] = []
        current_heading = [parsed.title]
        current_lines: list[str] = []
        for line in lines:
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
                if current_lines:
                    sections.append((current_heading, current_lines))
                    current_lines = []
                current_heading = [parsed.title, heading] if heading != parsed.title else [parsed.title]
            current_lines.append(line)
        if current_lines:
            sections.append((current_heading, current_lines))
        if not sections:
            return [([parsed.title], parsed.body)]
        return [(heading, "\n".join(section).strip()) for heading, section in sections if "\n".join(section).strip()]


__all__ = ["NoteChunk", "ObsidianChunker"]
