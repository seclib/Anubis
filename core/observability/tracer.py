"""Trace spans for ANUBIS action correlation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class SpanStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TraceSpan:
    trace_id: str
    span_id: str
    name: str
    component: str
    parent_span_id: str | None = None
    status: SpanStatus = SpanStatus.RUNNING
    start_time: datetime = field(default_factory=_utcnow)
    end_time: datetime | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("trace_id", "span_id", "name", "component"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty")
            object.__setattr__(self, field_name, str(getattr(self, field_name)).strip())
        object.__setattr__(self, "attributes", _freeze_mapping(self.attributes))
        if self.error is not None:
            object.__setattr__(self, "error", _freeze_mapping(self.error))

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return round((self.end_time - self.start_time).total_seconds() * 1000, 3)

    def finish(
        self,
        *,
        status: SpanStatus = SpanStatus.OK,
        attributes: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> "TraceSpan":
        merged_attributes = {**dict(self.attributes), **dict(attributes or {})}
        error_payload = None
        if error is not None:
            status = SpanStatus.ERROR
            error_payload = {
                "type": error.__class__.__name__,
                "message": str(error),
            }
        return TraceSpan(
            trace_id=self.trace_id,
            span_id=self.span_id,
            name=self.name,
            component=self.component,
            parent_span_id=self.parent_span_id,
            status=status,
            start_time=self.start_time,
            end_time=_utcnow(),
            attributes=merged_attributes,
            error=error_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "component": self.component,
            "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": None if self.end_time is None else self.end_time.isoformat(),
            "duration_ms": self.duration_ms,
            "attributes": dict(self.attributes),
            "error": None if self.error is None else dict(self.error),
        }


class Tracer:
    """In-memory tracing system with explicit span lifecycle."""

    def __init__(self) -> None:
        self._spans: dict[str, TraceSpan] = {}
        self._order: list[str] = []

    def start_span(
        self,
        *,
        name: str,
        component: str,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            trace_id=trace_id or f"trace_{uuid4().hex}",
            span_id=f"span_{uuid4().hex}",
            parent_span_id=parent_span_id,
            name=name,
            component=component,
            attributes=attributes or {},
        )
        self._spans[span.span_id] = span
        self._order.append(span.span_id)
        return span

    def finish_span(
        self,
        span_id: str,
        *,
        status: SpanStatus = SpanStatus.OK,
        attributes: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> TraceSpan:
        if span_id not in self._spans:
            raise KeyError(f"unknown span: {span_id}")
        current = self._spans[span_id]
        if current.end_time is not None:
            raise ValueError(f"span already finished: {span_id}")
        finished = current.finish(status=status, attributes=attributes, error=error)
        self._spans[span_id] = finished
        return finished

    def spans(self, trace_id: str | None = None) -> tuple[TraceSpan, ...]:
        spans = tuple(self._spans[span_id] for span_id in self._order)
        if trace_id is None:
            return spans
        return tuple(span for span in spans if span.trace_id == trace_id)


__all__ = ["SpanStatus", "TraceSpan", "Tracer"]
