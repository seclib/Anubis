"""Deterministic metrics collection for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class MetricType(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class MetricSample:
    sequence: int
    name: str
    metric_type: MetricType
    value: float
    labels: Mapping[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if not self.name.strip():
            raise ValueError("metric name cannot be empty")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(
            self,
            "labels",
            MappingProxyType({str(key): str(value) for key, value in dict(self.labels).items()}),
        )
        object.__setattr__(self, "value", float(self.value))

    @property
    def key(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return (self.name, tuple(sorted(self.labels.items())))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "name": self.name,
            "type": self.metric_type,
            "value": self.value,
            "labels": dict(self.labels),
        }


class MetricsCollector:
    """Append-only metrics collector with deterministic snapshots."""

    def __init__(self) -> None:
        self._samples: list[MetricSample] = []
        self._counter_values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauge_values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histogram_values: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}

    def increment(
        self,
        name: str,
        *,
        amount: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> MetricSample:
        if amount < 0:
            raise ValueError("counter increment cannot be negative")
        key = self._key(name, labels)
        value = self._counter_values.get(key, 0.0) + float(amount)
        self._counter_values[key] = value
        return self._append(name=name, metric_type=MetricType.COUNTER, value=value, labels=labels)

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> MetricSample:
        key = self._key(name, labels)
        self._gauge_values[key] = float(value)
        return self._append(name=name, metric_type=MetricType.GAUGE, value=value, labels=labels)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> MetricSample:
        key = self._key(name, labels)
        self._histogram_values.setdefault(key, []).append(float(value))
        return self._append(name=name, metric_type=MetricType.HISTOGRAM, value=value, labels=labels)

    def samples(self) -> tuple[MetricSample, ...]:
        return tuple(self._samples)

    def snapshot(self) -> dict[str, Any]:
        counters = {
            self._format_key(key): value for key, value in sorted(self._counter_values.items())
        }
        gauges = {
            self._format_key(key): value for key, value in sorted(self._gauge_values.items())
        }
        histograms = {}
        for key, values in sorted(self._histogram_values.items()):
            histograms[self._format_key(key)] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 6),
            }
        return {
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
            "sample_count": len(self._samples),
        }

    def _append(
        self,
        *,
        name: str,
        metric_type: MetricType,
        value: float,
        labels: Mapping[str, str] | None,
    ) -> MetricSample:
        sample = MetricSample(
            sequence=len(self._samples) + 1,
            name=name,
            metric_type=metric_type,
            value=value,
            labels=_freeze_mapping(labels),
        )
        self._samples.append(sample)
        return sample

    @staticmethod
    def _key(
        name: str,
        labels: Mapping[str, str] | None,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        return (name, tuple(sorted((str(key), str(value)) for key, value in dict(labels or {}).items())))

    @staticmethod
    def _format_key(key: tuple[str, tuple[tuple[str, str], ...]]) -> str:
        name, labels = key
        if not labels:
            return name
        suffix = ",".join(f"{label_key}={label_value}" for label_key, label_value in labels)
        return f"{name}{{{suffix}}}"


SystemVitals = MetricsCollector


__all__ = ["MetricSample", "MetricType", "MetricsCollector", "SystemVitals"]
