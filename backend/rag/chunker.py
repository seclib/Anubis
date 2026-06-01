from dataclasses import dataclass
from hashlib import sha256

from backend.vault.markdown import split_markdown_sections


@dataclass(frozen=True)
class Chunk:
    id: str
    path: str
    heading: str
    text: str
    line_start: int
    line_end: int
    hash: str


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
