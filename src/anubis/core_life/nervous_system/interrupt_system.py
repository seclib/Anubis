"""Emergency interrupt state."""

from dataclasses import dataclass


@dataclass(slots=True)
class InterruptSystem:
    interrupted: bool = False
    reason: str | None = None

    def trigger(self, reason: str) -> None:
        self.interrupted = True
        self.reason = reason

    def clear(self) -> None:
        self.interrupted = False
        self.reason = None

