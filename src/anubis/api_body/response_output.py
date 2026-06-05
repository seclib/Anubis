"""Response output schema."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResponseOutput:
    text: str
    status: str = "ok"

