"""Obsidian knowledge ingestion into local vectors and Qdrant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from knowledge.chunker import NoteChunk, ObsidianChunker
from knowledge.markdown_parser import MarkdownParser, ParsedNote
from knowledge.vault_scanner import VaultScanner
from memory import vector
from retrieval.embedding_pipeline import EmbeddingPipeline
from storage.qdrant import QdrantStore


class ObsidianIngestionPipeline:
    def __init__(
        self,
        *,
        scanner: VaultScanner | None = None,
        parser: MarkdownParser | None = None,
        chunker: ObsidianChunker | None = None,
        embeddings: EmbeddingPipeline | None = None,
        qdrant: QdrantStore | None = None,
    ) -> None:
        self.scanner = scanner or VaultScanner()
        self.parser = parser or MarkdownParser()
        self.chunker = chunker or ObsidianChunker()
        self.embeddings = embeddings or EmbeddingPipeline()
        self.qdrant = qdrant or QdrantStore()

    def ingest_vault(
        self,
        *,
        limit: int | None = None,
        force: bool = False,
        index_qdrant: bool = True,
    ) -> dict[str, Any]:
        notes = self.scanner.scan(limit=limit)
        store = vector.load_vector_store()
        existing_documents = [doc for doc in store.get("documents", []) if isinstance(doc, dict)]
        if force:
            existing_documents = [doc for doc in existing_documents if doc.get("kind") != "obsidian_chunk"]
        existing_chunk_hashes = {
            str(doc.get("content_hash"))
            for doc in existing_documents
            if doc.get("kind") == "obsidian_chunk" and doc.get("content_hash")
        }

        new_documents: list[dict[str, Any]] = []
        qdrant_points: list[dict[str, Any]] = []
        parsed_count = 0
        chunk_count = 0
        reused_count = 0

        for note in notes:
            parsed = self.parser.parse(note)
            parsed_count += 1
            chunks = self.chunker.chunk(parsed)
            for chunk in chunks:
                chunk_hash = vector._content_hash(chunk.text)
                if not force and chunk_hash in existing_chunk_hashes:
                    reused_count += 1
                    continue
                embedding = self.embeddings.embed_document(self._embedding_text(parsed, chunk))["embedding"]
                document = self._local_document(parsed, chunk, chunk_hash, embedding)
                new_documents.append(document)
                qdrant_points.append(
                    {
                        "id": document["id"],
                        "vector": embedding,
                        "payload": self._payload(parsed, chunk, chunk_hash),
                    }
                )
                chunk_count += 1

        if new_documents:
            if force:
                store["documents"] = existing_documents + new_documents
            else:
                store["documents"] = existing_documents + new_documents
            vector.save_vector_store(store)

        qdrant_result = {"ok": False, "indexed": 0, "status": "disabled"}
        if index_qdrant and qdrant_points:
            qdrant_result = self.qdrant.upsert_many(qdrant_points, vector_size=len(qdrant_points[0]["vector"]))

        return {
            "status": "ingested",
            "notes_scanned": len(notes),
            "notes_parsed": parsed_count,
            "chunks_created": chunk_count,
            "chunks_reused": reused_count,
            "local_documents": len(vector.load_vector_store().get("documents", [])),
            "qdrant": qdrant_result,
        }

    def _embedding_text(self, parsed: ParsedNote, chunk: NoteChunk) -> str:
        metadata = " ".join(
            [
                parsed.title,
                parsed.note.relative_path,
                " ".join(parsed.tags),
                " ".join(parsed.entities[:20]),
                " > ".join(chunk.heading_path),
            ]
        )
        return f"{metadata}\n\n{chunk.text}"

    def _local_document(
        self,
        parsed: ParsedNote,
        chunk: NoteChunk,
        chunk_hash: str,
        embedding: list[float],
    ) -> dict[str, Any]:
        return {
            "id": chunk.chunk_id,
            "kind": "obsidian_chunk",
            "source": parsed.note.relative_path,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk_hash,
            "text": chunk.text,
            "embedding": embedding,
            "metadata": self._payload(parsed, chunk, chunk_hash),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _payload(self, parsed: ParsedNote, chunk: NoteChunk, chunk_hash: str) -> dict[str, Any]:
        domain = self._domain(parsed)
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "parent_id": chunk.parent_id,
            "kind": "obsidian_chunk",
            "source": parsed.note.relative_path,
            "source_id": parsed.note.relative_path,
            "source_type": "obsidian",
            "domain": domain,
            "title": parsed.title,
            "path": parsed.note.relative_path,
            "url": parsed.frontmatter.get("source_url") or parsed.frontmatter.get("url"),
            "heading_path": chunk.heading_path,
            "tags": parsed.tags,
            "entities": parsed.entities,
            "backlinks": parsed.backlinks,
            "text": chunk.text[:4000],
            "content_hash": chunk_hash,
            "note_hash": parsed.note.content_hash,
            "quality_score": self._quality(parsed, chunk),
            "trust_score": self._trust(parsed),
            "freshness_score": 0.5,
            "updated_at": datetime.fromtimestamp(parsed.note.mtime, timezone.utc).isoformat(),
        }

    def _domain(self, parsed: ParsedNote) -> str:
        values = " ".join([parsed.note.relative_path, *parsed.tags, *parsed.entities]).lower()
        if "cve" in values or "vulnerability" in values:
            return "vulnerability"
        if "malware" in values or "yara" in values:
            return "malware_research"
        if "osint" in values or "recon" in values:
            return "osint"
        if "pentest" in values or "exploit" in values:
            return "pentesting"
        if "github" in values or "python" in values or "programming" in values:
            return "programming"
        return "knowledge"

    def _quality(self, parsed: ParsedNote, chunk: NoteChunk) -> float:
        score = 0.25
        if parsed.entities:
            score += 0.20
        if parsed.backlinks:
            score += 0.15
        if parsed.tags:
            score += 0.10
        if len(chunk.text) > 600:
            score += 0.15
        if "source" in parsed.frontmatter or "source_url" in parsed.frontmatter:
            score += 0.15
        return round(min(1.0, score), 6)

    def _trust(self, parsed: ParsedNote) -> float:
        if parsed.frontmatter.get("trust_score"):
            try:
                return float(parsed.frontmatter["trust_score"])
            except Exception:
                pass
        if parsed.frontmatter.get("source_url") or parsed.frontmatter.get("url"):
            return 0.65
        if parsed.note.relative_path.startswith(("10-sources/", "20-entities/", "50-syntheses/")):
            return 0.7
        return 0.45


_PIPELINE: ObsidianIngestionPipeline | None = None


def get_obsidian_ingestion_pipeline() -> ObsidianIngestionPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = ObsidianIngestionPipeline()
    return _PIPELINE


__all__ = ["ObsidianIngestionPipeline", "get_obsidian_ingestion_pipeline"]
