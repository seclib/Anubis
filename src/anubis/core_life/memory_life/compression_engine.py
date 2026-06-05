"""Memory compression primitives."""


class CompressionEngine:
    def compress(self, entries: tuple[str, ...], *, limit: int = 500) -> str:
        text = "\n".join(entries)
        return text[:limit]

