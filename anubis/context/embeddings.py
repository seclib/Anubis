from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import math
import re


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> tuple[float, ...]:
        ...


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            bucket = int.from_bytes(digest, "big") % self.dimensions
            vector[bucket] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return tuple(vector)
        return tuple(round(value / magnitude, 8) for value in vector)


class EmbeddingCache:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or HashEmbeddingProvider()
        self._cache: dict[str, tuple[float, ...]] = {}

    def embed(self, text: str) -> tuple[float, ...]:
        key = hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()
        if key not in self._cache:
            self._cache[key] = self.provider.embed(text)
        return self._cache[key]


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", text.lower())


__all__ = [
    "EmbeddingCache",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "cosine_similarity",
    "tokenize",
]
