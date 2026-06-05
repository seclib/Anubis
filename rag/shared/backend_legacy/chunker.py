from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Chunk:
    id: str
    path: str
    heading: str
    text: str
    line_start: int
    line_end: int
    hash: str


@dataclass(frozen=True)
class MarkdownSection:
    heading: str
    text: str
    line_start: int
    line_end: int


def split_markdown_sections(content: str) -> list[MarkdownSection]:
    lines = content.splitlines()
    sections: list[MarkdownSection] = []
    current_heading = "Document"
    start = 1
    buffer: list[str] = []

    for index, line in enumerate(lines, start=1):
        if line.startswith("# ") or line.startswith("## "):
            if buffer:
                sections.append(MarkdownSection(current_heading, "\n".join(buffer).strip(), start, index - 1))
            current_heading = line.lstrip("#").strip()
            start = index
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        sections.append(MarkdownSection(current_heading, "\n".join(buffer).strip(), start, len(lines)))

    return [section for section in sections if section.text]


def chunk_note(path: str, content: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, section in enumerate(split_markdown_sections(content)):
        digest = sha256(section.text.encode("utf-8")).hexdigest()
        chunks.append(
            Chunk(
                id=f"{path}::chunk-{index}",
                path=path,
                heading=section.heading,
                text=section.text,
                line_start=section.line_start,
                line_end=section.line_end,
                hash=digest,
            )
        )
    return chunks
