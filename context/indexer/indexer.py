from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from anubis.context.chunker import CodeChunker
from anubis.context.embeddings import EmbeddingCache, EmbeddingProvider
from anubis.context.scanner import RepositoryScanner
from anubis.context.schema import EmbeddedChunk, FileMetadata, RepositoryIndex


class RepositoryIndexer:
    def __init__(
        self,
        root: Path | str,
        embedding_provider: EmbeddingProvider | None = None,
        index_path: Path | str | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.embedding_cache = EmbeddingCache(embedding_provider)
        self.index_path = Path(index_path).resolve() if index_path else self.root / ".anubis_context_index.json"

    def index_repository(self) -> RepositoryIndex:
        scanner = RepositoryScanner(self.root)
        chunker = CodeChunker(self.root)
        files = scanner.scan()
        embedded: list[EmbeddedChunk] = []
        for file_metadata in files:
            for chunk in chunker.chunk_file(file_metadata):
                embedding_text = f"{chunk.file_path}\n{' '.join(chunk.symbols)}\n{chunk.content}"
                embedded.append(EmbeddedChunk(chunk=chunk, embedding=self.embedding_cache.embed(embedding_text)))
        return RepositoryIndex(root=str(self.root), files=files, chunks=tuple(embedded))

    def save(self, index: RepositoryIndex | None = None) -> RepositoryIndex:
        repository_index = index or self.index_repository()
        self.index_path.write_text(json.dumps(repository_index.to_dict(), indent=2), encoding="utf-8")
        return repository_index

    def load(self) -> RepositoryIndex:
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        files = tuple(FileMetadata(**item) for item in raw.get("files", []))
        chunks = []
        from anubis.context.schema import CodeChunk

        for item in raw.get("chunks", []):
            chunks.append(
                EmbeddedChunk(
                    chunk=CodeChunk(**item["chunk"]),
                    embedding=tuple(float(value) for value in item["embedding"]),
                )
            )
        return RepositoryIndex(root=str(raw["root"]), files=files, chunks=tuple(chunks))


def index_to_json(index: RepositoryIndex) -> str:
    return json.dumps(asdict(index), indent=2)


__all__ = ["RepositoryIndexer", "index_to_json"]
