"""Memory consolidation cycle."""

from anubis.core_life.memory_life.compression_engine import CompressionEngine


class SleepCycle:
    def __init__(self) -> None:
        self.compression = CompressionEngine()

    def consolidate(self, entries: tuple[str, ...]) -> str:
        return self.compression.compress(entries)

