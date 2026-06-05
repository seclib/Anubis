"""Continuous daily operation cycle."""

from dataclasses import dataclass


@dataclass(slots=True)
class DailyCycle:
    ticks: int = 0

    def tick(self) -> int:
        self.ticks += 1
        return self.ticks

