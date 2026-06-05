import unittest

from pipelines.update_pipeline import UpdatePipeline


class FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def upsert_chunks(self, domain, chunks):
        self.calls.append((domain, len(chunks)))
        return len(chunks)


class RagUpdatePipelineTest(unittest.TestCase):
    def test_demo_ingestion_builds_chunks_without_legacy_import_failures(self) -> None:
        store = FakeVectorStore()
        total = UpdatePipeline(store=store).ingest_demo()

        self.assertGreater(total, 0)
        self.assertEqual({domain for domain, _count in store.calls}, {"osint", "cve", "bugbounty"})


if __name__ == "__main__":
    unittest.main()
