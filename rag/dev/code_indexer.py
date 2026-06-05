from __future__ import annotations

from pathlib import Path

from rag.chunking import chunk_markdown
from rag.osint.schema import RagDocument
from rag.shared.schemas import VectorChunkRecord


_CODE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".rs",
    ".go",
    ".java",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
}


class CodeIndexer:
    domain = "dev"

    def index_path(self, path: str | Path) -> list[RagDocument]:
        root = Path(path)
        files = [root] if root.is_file() else [item for item in root.rglob("*") if item.is_file()]
        documents: list[RagDocument] = []
        for file_path in files:
            if file_path.suffix.lower() not in _CODE_SUFFIXES or file_path.stat().st_size > 1_000_000:
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel_path = file_path.as_posix()
            try:
                rel_path = file_path.relative_to(root if root.is_dir() else root.parent).as_posix()
            except ValueError:
                pass
            documents.append(
                RagDocument(
                    domain=self.domain,
                    title=rel_path,
                    body=text,
                    source_uri=file_path.as_posix(),
                    metadata={"path": rel_path, "language": file_path.suffix.lstrip(".")},
                )
            )
        return documents

    def chunk(self, document: RagDocument) -> list[VectorChunkRecord]:
        return [
            VectorChunkRecord(
                chunk_id=f"{document.doc_id}:{index}",
                doc_id=document.doc_id,
                domain=document.domain,
                text=text,
                source_uri=document.source_uri,
                title=document.title,
                metadata=dict(document.metadata),
            )
            for index, text in enumerate(chunk_markdown(document.body or document.title))
        ]


__all__ = ["CodeIndexer"]
