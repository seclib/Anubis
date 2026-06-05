from __future__ import annotations

from json import loads

from core.observability import (
    LogLevel,
    MetricsCollector,
    ObservabilityDashboardFeed,
    SpanStatus,
    StructuredLogger,
    Tracer,
)


def test_structured_logger_outputs_json_records() -> None:
    logger = StructuredLogger()

    record = logger.info(
        component="orchestrator",
        action="task.received",
        message="Task received",
        trace_id="trace_1",
        span_id="span_1",
        metadata={"task_id": "task_1"},
    )

    decoded = loads(record.to_json())
    assert decoded["level"] == LogLevel.INFO
    assert decoded["component"] == "orchestrator"
    assert decoded["metadata"] == {"task_id": "task_1"}
    assert logger.json_lines() == (record.to_json(),)


def test_logger_captures_errors_as_structured_records() -> None:
    logger = StructuredLogger()

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        record = logger.error(
            component="planner",
            action="plan.failed",
            message="Planning failed",
            trace_id="trace_1",
            error=exc,
        )

    assert record.level == LogLevel.ERROR
    assert record.metadata["error"] == {"type": "RuntimeError", "message": "boom"}


def test_tracer_tracks_span_lifecycle_and_errors() -> None:
    tracer = Tracer()

    parent = tracer.start_span(name="cognitive_loop", component="brain", trace_id="trace_1")
    child = tracer.start_span(
        name="planning",
        component="planner",
        trace_id=parent.trace_id,
        parent_span_id=parent.span_id,
    )
    finished_child = tracer.finish_span(child.span_id, error=ValueError("invalid plan"))
    finished_parent = tracer.finish_span(parent.span_id, status=SpanStatus.OK)

    assert finished_child.status == SpanStatus.ERROR
    assert finished_child.error == {"type": "ValueError", "message": "invalid plan"}
    assert finished_child.duration_ms is not None
    assert finished_parent.status == SpanStatus.OK
    assert [span.span_id for span in tracer.spans("trace_1")] == [
        parent.span_id,
        child.span_id,
    ]


def test_tracer_rejects_unknown_or_double_finished_spans() -> None:
    tracer = Tracer()
    span = tracer.start_span(name="task", component="executor")
    tracer.finish_span(span.span_id)

    try:
        tracer.finish_span("missing")
    except KeyError as exc:
        assert "unknown span" in str(exc)
    else:
        raise AssertionError("expected missing span error")

    try:
        tracer.finish_span(span.span_id)
    except ValueError as exc:
        assert "already finished" in str(exc)
    else:
        raise AssertionError("expected double finish error")


def test_metrics_collector_records_counters_gauges_and_histograms() -> None:
    metrics = MetricsCollector()

    metrics.increment("actions_total", labels={"component": "planner"})
    metrics.increment("actions_total", amount=2, labels={"component": "planner"})
    metrics.gauge("active_agents", 4)
    metrics.observe("task_duration_ms", 10)
    metrics.observe("task_duration_ms", 20)

    snapshot = metrics.snapshot()
    assert snapshot["counters"]["actions_total{component=planner}"] == 3.0
    assert snapshot["gauges"]["active_agents"] == 4.0
    assert snapshot["histograms"]["task_duration_ms"] == {
        "count": 2,
        "min": 10.0,
        "max": 20.0,
        "avg": 15.0,
    }
    assert snapshot["sample_count"] == 5


def test_metrics_reject_invalid_counter_increment() -> None:
    metrics = MetricsCollector()

    try:
        metrics.increment("actions_total", amount=-1)
    except ValueError as exc:
        assert "cannot be negative" in str(exc)
    else:
        raise AssertionError("expected negative counter rejection")


def test_dashboard_feed_combines_logs_traces_and_metrics() -> None:
    feed = ObservabilityDashboardFeed()
    span = feed.tracer.start_span(name="sandbox", component="execution", trace_id="trace_1")
    feed.logger.info(
        component="execution",
        action="sandbox.allowed",
        message="Sandbox allowed",
        trace_id=span.trace_id,
        span_id=span.span_id,
    )
    feed.metrics.increment("sandbox_decisions_total", labels={"decision": "allowed"})
    feed.tracer.finish_span(span.span_id)

    snapshot = feed.snapshot()
    assert snapshot["summary"] == {
        "log_count": 1,
        "span_count": 1,
        "open_span_count": 0,
        "error_log_count": 0,
        "error_span_count": 0,
    }
    assert snapshot["logs"][0]["trace_id"] == "trace_1"
    assert snapshot["traces"][0]["trace_id"] == "trace_1"
