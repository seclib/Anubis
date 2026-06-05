"""Self-reflection adapter over performance and architecture analysis."""

from dataclasses import dataclass

from anubis.self_improvement import PerformanceAnalyzer, PerformanceReport
from anubis.types import Event


@dataclass(slots=True)
class ReflectionEngine:
    analyzer: PerformanceAnalyzer

    async def reflect(self, events: tuple[Event, ...]) -> PerformanceReport:
        return await self.analyzer.analyze_events(events)

