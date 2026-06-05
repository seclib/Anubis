"""Dashboard feed schema for ANUBIS observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.observability.logger import StructuredLogger
from core.observability.metrics import MetricsCollector
from core.observability.tracer import Tracer


@dataclass(slots=True)
class ObservabilityDashboardFeed:
    logger: StructuredLogger = field(default_factory=StructuredLogger)
    tracer: Tracer = field(default_factory=Tracer)
    metrics: MetricsCollector = field(default_factory=MetricsCollector)

    def snapshot(self) -> dict[str, Any]:
        spans = [span.to_dict() for span in self.tracer.spans()]
        logs = [record.to_dict() for record in self.logger.records()]
        return {
            "logs": logs,
            "traces": spans,
            "metrics": self.metrics.snapshot(),
            "summary": {
                "log_count": len(logs),
                "span_count": len(spans),
                "open_span_count": len([span for span in spans if span["end_time"] is None]),
                "error_log_count": len([log for log in logs if log["level"] == "error"]),
                "error_span_count": len([span for span in spans if span["status"] == "error"]),
            },
        }


AgentActivityDashboard = ObservabilityDashboardFeed


__all__ = ["AgentActivityDashboard", "ObservabilityDashboardFeed"]
