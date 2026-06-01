from hashlib import sha256


class LocalEmbedder:
    """Deterministic placeholder embedder.

    Replace with Ollama or sentence-transformers in production.
    """

    dimensions = 32

    def embed(self, text: str) -> list[float]:
        digest = sha256(text.encode("utf-8")).digest()
        values = list(digest[: self.dimensions])
        return [value / 255 for value in values]
