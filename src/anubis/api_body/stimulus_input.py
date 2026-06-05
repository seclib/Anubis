"""Stimulus input schema."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StimulusInput:
    text: str
    source: str = "operator"

