"""Dynamic focus selection for competing stimuli."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttentionSignal:
    name: str
    priority: int
    reason: str = ""


class AttentionEngine:
    def focus(self, signals: tuple[AttentionSignal, ...]) -> AttentionSignal | None:
        if not signals:
            return None
        return sorted(signals, key=lambda signal: (-signal.priority, signal.name))[0]

