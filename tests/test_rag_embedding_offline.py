import unittest

from rag.shared.embedding import EmbeddingPipeline


class RagEmbeddingOfflineTest(unittest.TestCase):
    def test_default_embedding_provider_is_deterministic_and_local(self) -> None:
        pipeline = EmbeddingPipeline()

        first = pipeline.embed("local first memory retrieval")
        second = pipeline.embed("local first memory retrieval")

        self.assertEqual(first, second)
        self.assertEqual(len(first), pipeline.dimensions)
        self.assertIsNone(pipeline._model)


if __name__ == "__main__":
    unittest.main()
