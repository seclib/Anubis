from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.chunking import chunk_markdown
from rag.osint.schema import RagDocument
from rag.shared.io import load_json_records
from rag.shared.schemas import VectorChunkRecord
from rag.shared.utils import clean_text, stable_id


class CveParser:
    def parse_kev_item(self, item: dict[str, Any]) -> RagDocument:
        cve_id = clean_text(item.get("cveID") or item.get("cve") or item.get("id") or "CVE")
        title = clean_text(item.get("vulnerabilityName") or item.get("title") or cve_id)
        body = "\n".join(
            part
            for part in (
                title,
                clean_text(item.get("vendorProject")),
                clean_text(item.get("product")),
                clean_text(item.get("shortDescription") or item.get("description")),
                clean_text(item.get("requiredAction")),
            )
            if part
        )
        return RagDocument(
            domain="cve",
            title=f"{cve_id} {title}".strip(),
            body=body or title,
            source_uri=clean_text(item.get("source_uri") or f"kev:{cve_id}"),
            metadata={"cves": [cve_id], "source": "kev", "raw": item},
        )

    def parse_nvd_item(self, item: dict[str, Any]) -> RagDocument:
        cve = item.get("cve") if isinstance(item.get("cve"), dict) else item
        cve_id = clean_text(cve.get("id") or cve.get("CVE_data_meta", {}).get("ID") or item.get("id") or "CVE")
        descriptions = cve.get("descriptions") or cve.get("description", {}).get("description_data") or []
        description = ""
        if isinstance(descriptions, list) and descriptions:
            first = descriptions[0]
            description = clean_text(first.get("value") if isinstance(first, dict) else first)
        title = clean_text(cve.get("title") or cve_id)
        return RagDocument(
            domain="cve",
            title=title,
            body=description or title,
            source_uri=clean_text(item.get("source_uri") or f"nvd:{cve_id}"),
            metadata={"cves": [cve_id], "source": "nvd", "raw": item},
        )


class CveIngestion:
    domain = "cve"

    def __init__(self, parser: CveParser | None = None) -> None:
        self.parser = parser or CveParser()

    def load_nvd_json(self, path: str | Path) -> list[RagDocument]:
        records = load_json_records(path, list_keys=("vulnerabilities", "CVE_Items", "items", "data", "records", "results"))
        return [self.parser.parse_nvd_item(record) for record in records]

    def load_kev_json(self, path: str | Path) -> list[RagDocument]:
        records = load_json_records(path, list_keys=("vulnerabilities", "items", "data", "records", "results"))
        return [self.parser.parse_kev_item(record) for record in records]

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


__all__ = ["CveIngestion", "CveParser"]
