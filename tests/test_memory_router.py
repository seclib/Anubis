import unittest

from retrieval.memory_router import MemoryRouter, QueryClassifier


class FakeRetriever:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query, limit=8):
        self.calls.append((query, limit))
        return self.rows[:limit]


class MemoryRouterTest(unittest.TestCase):
    def test_classifier_routes_procedures_to_obsidian_truth(self) -> None:
        classification = QueryClassifier().classify("what is the canonical firewall hardening procedure")

        self.assertEqual(classification.intent, "procedural")
        self.assertGreater(classification.obsidian_weight, classification.qdrant_weight)

    def test_truth_query_prefers_obsidian(self) -> None:
        obsidian = FakeRetriever(
            [
                {
                    "path": "skills/firewall.md",
                    "heading": "Firewall Rules",
                    "text": "Canonical firewall rule: deny inbound by default.",
                    "tags": ["skill", "policy"],
                    "keywords": ["canonical", "firewall", "rule"],
                    "confidence": 0.95,
                }
            ]
        )
        qdrant = FakeRetriever(
            [
                {
                    "text": "Similar old memory says allow inbound traffic by default.",
                    "score": 0.92,
                }
            ]
        )

        result = MemoryRouter(obsidian=obsidian, qdrant=qdrant).route(
            "what is the canonical firewall rule",
            limit=4,
        )

        self.assertEqual(result.decision.selected_memory_source, "obsidian")
        self.assertEqual(result.context[0].path, "skills/firewall.md")
        self.assertTrue(result.context[0].score > 0)

    def test_semantic_query_prefers_qdrant_similarity(self) -> None:
        obsidian = FakeRetriever(
            [
                {
                    "path": "skills/general.md",
                    "text": "General operational checklist.",
                    "keywords": ["general", "checklist"],
                }
            ]
        )
        qdrant = FakeRetriever(
            [
                {
                    "text": "A similar previous incident involved qdrant timeout recovery.",
                    "score": 0.91,
                }
            ]
        )

        result = MemoryRouter(obsidian=obsidian, qdrant=qdrant).route(
            "find similar qdrant timeout incidents",
            limit=4,
        )

        self.assertEqual(result.classification.intent, "semantic")
        self.assertEqual(result.decision.selected_memory_source, "qdrant")
        self.assertEqual(result.context[0].source, "qdrant")

    def test_conflict_prioritizes_obsidian_over_qdrant(self) -> None:
        obsidian = FakeRetriever(
            [
                {
                    "path": "memory/truth.md",
                    "text": "Anubis must not use Qdrant as the truth layer. Obsidian is truth memory.",
                    "tags": ["truth"],
                    "keywords": ["anubis", "qdrant", "truth", "layer"],
                    "confidence": 0.95,
                }
            ]
        )
        qdrant = FakeRetriever(
            [
                {
                    "text": "Anubis must use Qdrant as the truth layer.",
                    "score": 0.99,
                }
            ]
        )

        result = MemoryRouter(obsidian=obsidian, qdrant=qdrant).route(
            "Should Anubis use Qdrant as the truth layer?",
            limit=4,
        )

        self.assertTrue(result.decision.conflict_flag)
        self.assertEqual(result.decision.selected_memory_source, "obsidian")

    def test_context_merger_deduplicates_and_limits_results(self) -> None:
        obsidian = FakeRetriever(
            [
                {"path": "a.md", "text": "Procedure alpha step one.", "keywords": ["procedure", "alpha"]},
                {"path": "a.md", "text": "Procedure alpha step one.", "keywords": ["procedure", "alpha"]},
                {"path": "b.md", "text": "Procedure alpha step two.", "keywords": ["procedure", "alpha"]},
            ]
        )

        result = MemoryRouter(obsidian=obsidian, qdrant=FakeRetriever([])).route(
            "procedure alpha",
            limit=2,
        )

        self.assertLessEqual(len(result.context), 2)
        self.assertEqual(len({item.content for item in result.context}), len(result.context))


if __name__ == "__main__":
    unittest.main()
