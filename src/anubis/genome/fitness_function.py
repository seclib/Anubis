"""Fitness function for ANUBIS evolution."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FitnessScore:
    safety: float
    reliability: float
    performance: float
    simplicity: float

    @property
    def total(self) -> float:
        return self.safety * 0.4 + self.reliability * 0.3 + self.performance * 0.2 + self.simplicity * 0.1


def score_fitness(*, safety: float, reliability: float, performance: float, simplicity: float) -> FitnessScore:
    return FitnessScore(
        safety=safety,
        reliability=reliability,
        performance=performance,
        simplicity=simplicity,
    )

