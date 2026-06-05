from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.chunking import chunk_markdown
from rag.osint.schema import RagDocument
from rag.shared.io import load_json_records
from rag.shared.schemas import VectorChunkRecord
from rag.shared.utils import clean_text, stable_id


class BugBountyIngestion:
    domain = "bugbounty"

    def load_jsonl(self, path: str | Path) -> list[RagDocument]:
        return [self.from_record(record) for record in load_json_records(path)]

    def from_record(self, record: dict[str, Any]) -> RagDocument:
        title = clean_text(record.get("title") or record.get("vulnerability") or record.get("summary") or "Bug bounty report")
        body = clean_text(
            record.get("body")
            or record.get("content")
            or record.get("text")
            or record.get("description")
            or record.get("impact")
            or title
        )
        source_uri = clean_text(record.get("source_uri") or record.get("url") or record.get("program") or stable_id(title, body))
        metadata = {key: value for key, value in record.items() if key not in {"title", "vulnerability", "summary", "body", "content", "text", "description", "impact", "source_uri", "url", "program"}}
        return RagDocument(domain=self.domain, title=title, body=body, source_uri=source_uri, metadata=metadata)

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


__all__ = ["BugBountyIngestion"]
