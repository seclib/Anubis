"""Metric samples for system vitals."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from anubis.types import utcnow


@dataclass(frozen=True, slots=True)
class MetricSample:
    name: str
    value: float
    unit: str
    labels: Mapping[str, Any] = field(default_factory=dict)
    timestamp: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "labels", MappingProxyType(dict(self.labels)))


@dataclass(frozen=True, slots=True)
class SystemVitals:
    metrics: tuple[MetricSample, ...]

