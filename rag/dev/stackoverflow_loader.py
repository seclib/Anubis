from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.osint.schema import RagDocument
from rag.shared.io import load_json_records
from rag.shared.utils import clean_text, stable_id


class StackOverflowLoader:
    domain = "dev"

    def load_jsonl(self, path: str | Path) -> list[RagDocument]:
        return [self.from_record(record) for record in load_json_records(path)]

    def from_record(self, record: dict[str, Any]) -> RagDocument:
        title = clean_text(record.get("title") or record.get("question") or "Stack Overflow item")
        body = clean_text(record.get("body") or record.get("answer") or record.get("text") or record.get("content") or title)
        source_uri = clean_text(record.get("source_uri") or record.get("url") or stable_id(title, body))
        return RagDocument(
            domain=self.domain,
            title=title,
            body=body,
            source_uri=source_uri,
            metadata={"source": "stackoverflow", "tags": record.get("tags") or []},
        )


__all__ = ["StackOverflowLoader"]
