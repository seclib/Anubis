from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from anubis.memory import MemoryRecord
from anubis.types import Event, EventType


@dataclass(frozen=True, slots=True)
class FitnessScore:
    speed: float
    stability: float
    task_success_rate: float
    memory_efficiency: float

    @property
    def total(self) -> float:
        return (
            self.speed * 0.2
            + self.stability * 0.35
            + self.task_success_rate * 0.35
            + self.memory_efficiency * 0.1
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "speed": self.speed,
            "stability": self.stability,
            "task_success_rate": self.task_success_rate,
            "memory_efficiency": self.memory_efficiency,
            "total": self.total,
        }


class FitnessFunction:
    """Deterministic health scoring for ANUBIS evolution."""

    def evaluate(
        self,
        events: Sequence[Event],
        *,
        memory_records: Sequence[MemoryRecord] = (),
    ) -> FitnessScore:
        finished = sum(
            1 for event in events if event.type in {EventType.TASK_SUCCEEDED, EventType.TASK_FAILED}
        )
        succeeded = sum(1 for event in events if event.type == EventType.TASK_SUCCEEDED)
        failed = sum(1 for event in events if event.type == EventType.TASK_FAILED)
        retries = sum(1 for event in events if event.type == EventType.EXECUTION_RETRY_SCHEDULED)
        denials = sum(1 for event in events if event.type == EventType.SANDBOX_DENIED)
        kill_switches = sum(
            1 for event in events if event.type == EventType.SAFETY_KILL_SWITCH_TRIGGERED
        )

        success_rate = succeeded / finished if finished else 1.0
        retry_pressure = retries / finished if finished else 0.0
        speed = _clamp(1.0 - retry_pressure)
        instability = (failed + denials + kill_switches * 2) / max(finished, 1)
        stability = _clamp(1.0 - instability)
        memory_efficiency = self._memory_efficiency(events, memory_records)

        return FitnessScore(
            speed=speed,
            stability=stability,
            task_success_rate=_clamp(success_rate),
            memory_efficiency=memory_efficiency,
        )

    def _memory_efficiency(
        self,
        events: Sequence[Event],
        memory_records: Sequence[MemoryRecord],
    ) -> float:
        if not memory_records:
            return 1.0
        event_density = len(events) / max(len(memory_records), 1)
        duplicate_contents = len(memory_records) - len({record.content for record in memory_records})
        density_penalty = max(0.0, event_density - 50.0) / 100.0
        duplicate_penalty = duplicate_contents / len(memory_records)
        return _clamp(1.0 - density_penalty - duplicate_penalty)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
