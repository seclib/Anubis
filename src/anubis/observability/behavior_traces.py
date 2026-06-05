"""Decision and behavior trace schemas."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from anubis.types import utcnow


@dataclass(frozen=True, slots=True)
class TraceSpan:
    name: str
    component: str
    trace_id: str = field(default_factory=lambda: f"trace_{uuid4().hex}")
    parent_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    started_at: object = field(default_factory=utcnow)
    ended_at: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

