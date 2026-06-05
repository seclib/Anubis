"""Internal experiment runner for safe A/B comparisons."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    name: str
    score: float


class ExperimentRunner:
    def choose_best(self, results: tuple[ExperimentResult, ...]) -> ExperimentResult | None:
        if not results:
            return None
        return sorted(results, key=lambda result: (-result.score, result.name))[0]

