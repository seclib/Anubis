"""Agent energy and execution cost model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnergyCost:
    cpu: float = 1.0
    memory: float = 1.0
    risk: float = 0.0

    @property
    def total(self) -> float:
        return self.cpu + self.memory + self.risk

