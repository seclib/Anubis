from __future__ import annotations

from pathlib import Path
import hashlib
import re

from anubis.context.schema import CodeChunk, FileMetadata
from anubis.context.symbols import extract_exports, extract_imports, extract_symbols


MAX_CHUNK_LINES = 90
OVERLAP_LINES = 12


class CodeChunker:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def chunk_file(self, metadata: FileMetadata) -> tuple[CodeChunk, ...]:
        path = self.root / metadata.path
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ()
        lines = text.splitlines()
        ranges = self._symbol_ranges(lines, metadata.language)
        if not ranges:
            ranges = self._section_ranges(lines)
        chunks: list[CodeChunk] = []
        for index, (start, end) in enumerate(ranges):
            content = "\n".join(lines[start:end]).strip()
            if not content:
                continue
            symbols = tuple(extract_symbols(content, metadata.language))
            imports = tuple(extract_imports(content, metadata.language))
            exports = tuple(extract_exports(content, metadata.language))
            chunks.append(
                CodeChunk(
                    id=_chunk_id(metadata.path, start, end, content),
                    file_path=metadata.path,
                    language=metadata.language,
                    content=content,
                    start_line=start + 1,
                    end_line=end,
                    symbols=symbols or metadata.symbols,
                    imports=imports or metadata.imports,
                    exports=exports,
                    metadata={"chunk_index": index},
                )
            )
        return tuple(chunks)

    def _symbol_ranges(self, lines: list[str], language: str) -> list[tuple[int, int]]:
        pattern = re.compile(
            r"^\s*(?:async\s+def|def|class|export\s+class|export\s+function|function|export\s+const|const)\s+"
        )
        starts = [index for index, line in enumerate(lines) if pattern.search(line)]
        ranges: list[tuple[int, int]] = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)
            if end - start > MAX_CHUNK_LINES:
                ranges.extend(self._split_range(start, end))
            else:
                ranges.append((start, end))
        return ranges

    def _section_ranges(self, lines: list[str]) -> list[tuple[int, int]]:
        if not lines:
            return []
        return self._split_range(0, len(lines))

    def _split_range(self, start: int, end: int) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        cursor = start
        while cursor < end:
            chunk_end = min(end, cursor + MAX_CHUNK_LINES)
            ranges.append((cursor, chunk_end))
            if chunk_end >= end:
                break
            cursor = max(cursor + 1, chunk_end - OVERLAP_LINES)
        return ranges


def _chunk_id(path: str, start: int, end: int, content: str) -> str:
    digest = hashlib.blake2b(f"{path}:{start}:{end}:{content}".encode("utf-8"), digest_size=8).hexdigest()
    return f"{path}:{start + 1}-{end}:{digest}"


__all__ = ["CodeChunker"]
