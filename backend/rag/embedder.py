from functools import cached_property
from hashlib import sha256
import logging

import requests

from backend.core.config import settings


logger = logging.getLogger("anubis.rag.embedder")


class LocalEmbedder:
    """Ollama embedding adapter with deterministic local fallback."""

    fallback_dimensions = 32

    def embed(self, text: str) -> list[float]:
        try:
            response = requests.post(
                f"{settings.ollama_url.rstrip('/')}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
                timeout=30,
            )
            response.raise_for_status()
            embedding = response.json().get("embedding")
            if isinstance(embedding, list) and embedding:
                return [float(value) for value in embedding]
        except Exception as exc:  # pragma: no cover - depends on local Ollama availability
            logger.warning("ollama embeddings unavailable; using deterministic fallback: %s", exc)
        digest = sha256(text.encode("utf-8")).digest()
        values = list(digest[: self.fallback_dimensions])
        return [value / 255 for value in values]

    @cached_property
    def dimensions(self) -> int:
        return len(self.embed("anubis embedding dimension probe"))
