from __future__ import annotations

from pathlib import Path

from rag.bugbounty.ingestion import BugBountyIngestion
from rag.cve.cve_ingestion import CveIngestion
from rag.dev.code_indexer import CodeIndexer
from rag.dev.stackoverflow_loader import StackOverflowLoader
from rag.osint.ingestion import OsintIngestion
from rag.osint.schema import RagDocument
from rag.shared.qdrant_client import QdrantVectorStore


class UpdatePipeline:
    def __init__(self, store: QdrantVectorStore | None = None) -> None:
        self.store = store or QdrantVectorStore()
        self.osint = OsintIngestion()
        self.cve = CveIngestion()
        self.bugbounty = BugBountyIngestion()
        self.dev = CodeIndexer()
        self.stackoverflow = StackOverflowLoader()

    def ingest_documents(self, documents: list[RagDocument]) -> int:
        chunks_by_domain: dict[str, list] = {}
        for document in documents:
            chunks = self._chunk_document(document)
            chunks_by_domain.setdefault(document.domain, []).extend(chunks)
        total = 0
        for domain, chunks in chunks_by_domain.items():
            total += self.store.upsert_chunks(domain, chunks)
        return total

    def ingest_osint_jsonl(self, path: str | Path) -> int:
        return self.ingest_documents(self.osint.load_jsonl(path))

    def ingest_nvd_json(self, path: str | Path) -> int:
        return self.ingest_documents(self.cve.load_nvd_json(path))

    def ingest_kev_json(self, path: str | Path) -> int:
        return self.ingest_documents(self.cve.load_kev_json(path))

    def ingest_bugbounty_jsonl(self, path: str | Path) -> int:
        return self.ingest_documents(self.bugbounty.load_jsonl(path))

    def ingest_code_path(self, path: str | Path) -> int:
        return self.ingest_documents(self.dev.index_path(path))

    def ingest_stackoverflow_jsonl(self, path: str | Path) -> int:
        return self.ingest_documents(self.stackoverflow.load_jsonl(path))

    def ingest_demo(self) -> int:
        docs = [
            self.osint.from_record({
                "title": "Observed exploitation infrastructure",
                "body": "malicious.example resolved to 203.0.113.10 and was mentioned in reporting about CVE-2025-12345 exploitation.",
                "source_uri": "demo:osint:1",
            }),
            self.cve.parser.parse_kev_item({
                "cveID": "CVE-2025-12345",
                "vendorProject": "ExampleSoft",
                "product": "Example Gateway",
                "vulnerabilityName": "Remote command execution",
                "requiredAction": "Apply vendor patch immediately.",
            }),
            self.bugbounty.from_record({
                "title": "SSRF via webhook target",
                "body": "Impact: attacker can reach metadata service. Payload: `http://169.254.169.254/latest/meta-data/` Remediation: block link-local addresses.",
                "source_uri": "demo:bugbounty:1",
            }),
        ]
        return self.ingest_documents(docs)

    def _chunk_document(self, document: RagDocument):
        if document.domain == "cve":
            return self.cve.chunk(document)
        if document.domain == "bugbounty":
            return self.bugbounty.chunk(document)
        if document.domain == "dev":
            return self.dev.chunk(document)
        return self.osint.chunk(document)
