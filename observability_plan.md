# ANUBIS Production Observability Plan

Date: 2026-06-05

## Goal

Design production observability for ANUBIS.

Requirements:

- metrics
- tracing
- logs
- health checks

This is a design artifact only. It does not modify runtime behavior.

## Current State

ANUBIS already contains observability primitives:

- `core/observability/StructuredLogger`
- `core/observability/Tracer`
- `core/observability/MetricsCollector`
- `core/observability/DashboardFeed`
- `core/security/AuditLogger`
- `src/anubis/observability/*`
- `config/logging.yaml`
- `config/audit_policy.yaml`

Current limitations:

- logs are in-memory
- traces are in-memory
- metrics are in-memory
- audit records are in-memory
- no external exporter exists
- no `/health` HTTP runtime exists despite route constants
- no durable retention is enforced
- duplicate observability schemas exist in `core/` and `src/anubis/`

Production implication:

ANUBIS needs a single observability contract that preserves local-first operation while allowing export to standard telemetry systems.

## Observability Principles

### 1. Structured by Default

All telemetry should be machine-readable.

Required common fields:

- timestamp
- service name
- environment
- version
- trace id
- span id when available
- task id when available
- component
- action
- severity or status

### 2. Correlated Across Signals

Metrics, logs, traces, audit records, terminal commands, and health checks should share correlation identifiers.

Primary correlation fields:

```text
trace_id
span_id
task_id
request_id
command_id
agent_role
workspace_id
```

### 3. Local-First, Export-Ready

ANUBIS should work without network access.

Production observability should support:

- local JSONL files
- local dashboard feed
- optional OpenTelemetry export
- optional Prometheus scrape endpoint
- optional log forwarding

No telemetry should require a cloud service.

### 4. Safe by Design

Observability must not leak secrets.

Rules:

- redact before persistence
- redact before export
- do not log prompt secrets or vault values
- do not log raw `.env` contents
- do not store raw authorization headers
- preserve command shape without exposing secret values

### 5. Audit Is Separate but Correlated

Audit logs and application logs have different retention and integrity requirements.

Application logs answer:

```text
What happened operationally?
```

Audit records answer:

```text
Who or what attempted an action, was it allowed, and why?
```

They should share `trace_id`, but audit records should remain append-only and hash-chained.

## Target Architecture

```text
Runtime Components
  -> Observability Facade
     -> Metrics API
     -> Tracing API
     -> Logging API
     -> Health API
     -> Audit API
        -> Redaction Layer
        -> Local Durable Store
        -> Export Pipeline
           -> JSONL
           -> OpenTelemetry
           -> Prometheus
           -> Dashboard Feed
```

## Canonical Components

### Observability Facade

Responsibilities:

- provide one import surface for telemetry
- create and propagate context
- expose metrics, traces, logs, and health
- enforce redaction
- attach task/workspace metadata
- route telemetry to configured sinks

Canonical package candidate:

```text
core/observability
```

Rationale:

- active graph runtime already uses `core.observability`
- current `core` logger/tracer/metrics are deterministic and tested
- duplication audit recommends merging duplicate observability systems into one canonical contract

### Telemetry Context

Every execution should have a telemetry context.

```text
TelemetryContext
  trace_id
  span_id
  task_id
  request_id
  workspace_id
  branch
  actor
  environment
```

Context should be propagated through:

- graph nodes
- agents
- memory
- retrieval
- sandbox validation
- terminal commands
- Git workflows
- plugin execution
- Docker operations

### Redaction Layer

Responsibilities:

- inspect structured fields
- inspect terminal output chunks
- redact known secret keys
- redact token-like values
- preserve metadata that a redaction occurred

Redaction marker:

```text
[REDACTED: secret-like value]
```

Redaction metrics:

- `anubis_redaction_total`
- `anubis_redaction_fields_total`
- `anubis_secret_output_block_total`

### Durable Local Store

Recommended local storage:

```text
.anubis/observability/
  logs.jsonl
  traces.jsonl
  metrics.jsonl
  audit.jsonl
  health.jsonl
```

Properties:

- append-only writes
- rotation by size and date
- crash-safe flush for audit records
- human-readable JSONL
- exportable without a database

Future production option:

- SQLite for indexed local queries
- OpenTelemetry Collector for external export

## Metrics

### Metric Naming

Use Prometheus-compatible names:

```text
anubis_<subsystem>_<measurement>_<unit>
```

Examples:

- `anubis_graph_runs_total`
- `anubis_graph_run_duration_ms`
- `anubis_agent_execution_duration_ms`
- `anubis_rag_retrieval_duration_ms`
- `anubis_memory_records_total`

### Metric Types

Supported types:

- counter
- gauge
- histogram

Current `MetricsCollector` already supports these types in-memory. Production should add export-friendly naming, labels, and histogram buckets.

### Required Runtime Metrics

Graph metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_graph_runs_total` | counter | `status`, `source` |
| `anubis_graph_run_duration_ms` | histogram | `status`, `source` |
| `anubis_graph_node_duration_ms` | histogram | `node`, `status` |
| `anubis_graph_node_errors_total` | counter | `node`, `error_type` |
| `anubis_graph_transitions_total` | counter | `from_node`, `to_node` |

Agent metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_agent_runs_total` | counter | `agent_role`, `status` |
| `anubis_agent_duration_ms` | histogram | `agent_role`, `status` |
| `anubis_agent_review_failures_total` | counter | `reason` |
| `anubis_agent_context_tokens_estimated` | histogram | `agent_role` |

Memory and RAG metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_memory_records_total` | gauge | `namespace`, `memory_type` |
| `anubis_memory_writes_total` | counter | `namespace`, `memory_type`, `status` |
| `anubis_memory_retrieval_duration_ms` | histogram | `namespace`, `status` |
| `anubis_rag_index_duration_ms` | histogram | `collection`, `status` |
| `anubis_rag_retrieval_duration_ms` | histogram | `collection`, `status` |
| `anubis_rag_results_returned` | histogram | `collection` |
| `anubis_embedding_cache_hits_total` | counter | `collection` |
| `anubis_embedding_cache_misses_total` | counter | `collection` |

Sandbox and security metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_sandbox_decisions_total` | counter | `decision`, `reason` |
| `anubis_permission_decisions_total` | counter | `decision`, `permission` |
| `anubis_audit_records_total` | counter | `event_type` |
| `anubis_kill_switch_active` | gauge | none |
| `anubis_threat_findings_total` | counter | `severity`, `finding_type` |

Terminal and execution metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_command_runs_total` | counter | `origin`, `status`, `risk_class` |
| `anubis_command_duration_ms` | histogram | `origin`, `status` |
| `anubis_command_output_bytes_total` | counter | `stream` |
| `anubis_command_denials_total` | counter | `reason` |
| `anubis_terminal_stream_lag_ms` | histogram | `tab` |

Git metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_git_operations_total` | counter | `operation`, `status` |
| `anubis_git_operation_duration_ms` | histogram | `operation`, `status` |
| `anubis_pr_created_total` | counter | `provider`, `draft` |
| `anubis_pr_ci_status_total` | counter | `provider`, `status` |

System metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_process_uptime_seconds` | gauge | none |
| `anubis_process_memory_rss_bytes` | gauge | none |
| `anubis_process_cpu_percent` | gauge | none |
| `anubis_open_files` | gauge | none |
| `anubis_docker_image_size_bytes` | gauge | `image` |

### Metric Label Policy

Avoid high-cardinality labels.

Allowed labels:

- subsystem
- component
- status
- node
- agent_role
- namespace
- source
- operation
- provider

Forbidden labels:

- raw prompt
- file path by default
- command text by default
- error message by default
- branch name by default in global metrics
- user-specific secret references

File paths and command text belong in logs/traces, not metric labels.

### SLO-Oriented Metrics

Recommended initial SLOs:

| SLO | Target |
| --- | ---: |
| CLI cold startup p95 | `<500 ms` |
| Graph run p95 without external services | `<1 s` |
| RAG retrieval p95 local | `<100 ms` |
| Terminal stream append p95 | `<50 ms` |
| Health endpoint p95 | `<100 ms` |
| Sandbox decision p95 | `<10 ms` |
| Error rate for graph runs | `<1%` |

Current measured baselines:

- cold CLI startup median: `220.96 ms`
- cold CLI startup p95: `241.61 ms`
- maximum RSS: about `28.57 MiB`
- core retrieval p95 over 1,000 records: `4.60 ms`
- scoped RAG retrieval p95 over 1,000 records: `8.47 ms`
- core agent latencies: sub-millisecond p95
- Docker image size: `123.17 MB`

## Tracing

### Trace Model

One user task should produce one root trace.

```text
trace: task/request
  span: input
  span: context_builder
  span: planner
  span: agent_dispatch
  span: executor
  span: sandbox_validation
  span: terminal_command
  span: memory_write
  span: rag_retrieval
  span: reviewer
  span: output
```

### Required Span Fields

```text
TraceSpan
  trace_id
  span_id
  parent_span_id
  name
  component
  status
  start_time
  end_time
  duration_ms
  attributes
  error
```

Existing `core.observability.TraceSpan` already matches most of this.

### Span Naming

Use stable names:

```text
graph.run
graph.node.input
graph.node.planner
graph.node.agent_dispatch
graph.node.execution_sandbox
graph.node.memory
graph.node.reflection
graph.node.output
agent.run
memory.write
rag.retrieve
sandbox.validate
command.run
git.operation
docker.operation
plugin.execute
```

### Span Attributes

Recommended attributes:

- `task.source`
- `graph.node`
- `agent.role`
- `memory.namespace`
- `rag.collection`
- `sandbox.decision`
- `command.origin`
- `command.risk_class`
- `git.operation`
- `plugin.id`
- `error.type`

Never include:

- raw prompt text
- secret values
- full command output
- large diffs
- file contents

### Trace Export

Supported exporters:

1. JSONL local trace file
2. OpenTelemetry Protocol exporter
3. dashboard feed for local UI

Default:

```text
local JSONL only
```

Production option:

```text
OTLP endpoint configured explicitly
```

### Sampling

Default local mode:

```text
sample all traces
```

Production high-volume mode:

- sample all failed traces
- sample all security-denied traces
- sample all slow traces
- sample configurable percentage of successful traces

## Logs

### Log Format

Use JSON Lines.

```json
{
  "timestamp": "2026-06-05T12:00:00Z",
  "level": "info",
  "service": "anubis",
  "environment": "production",
  "component": "graph.runner",
  "action": "graph.node.completed",
  "message": "Graph node completed.",
  "trace_id": "trace_...",
  "span_id": "span_...",
  "task_id": "task_...",
  "metadata": {
    "node": "planner",
    "duration_ms": 3.2
  }
}
```

### Log Levels

```text
debug: detailed local diagnosis
info: normal lifecycle events
warning: unusual but recoverable conditions
error: failed operation
critical: kill switch, sandbox escape attempt, unrecoverable corruption
```

### Required Application Events

Graph events:

- `graph.run.started`
- `graph.run.completed`
- `graph.run.failed`
- `graph.node.started`
- `graph.node.completed`
- `graph.node.failed`
- `graph.route.selected`

Agent events:

- `agent.run.started`
- `agent.run.completed`
- `agent.run.failed`
- `agent.review.failed`

Memory/RAG events:

- `memory.write.completed`
- `memory.write.failed`
- `memory.retrieve.completed`
- `rag.index.completed`
- `rag.retrieve.completed`
- `rag.cache.hit`
- `rag.cache.miss`

Execution/terminal events:

- `command.queued`
- `command.approval.requested`
- `command.started`
- `command.completed`
- `command.failed`
- `command.denied`
- `command.timed_out`

Git events:

- `git.branch.created`
- `git.diff.generated`
- `git.commit.created`
- `git.pr.created`
- `git.pr.status.updated`

Security events:

- `permission.allowed`
- `permission.denied`
- `sandbox.allowed`
- `sandbox.denied`
- `threat.finding`
- `kill_switch.triggered`

### Log Retention

Default local retention:

```text
application logs: 14 days
failed task logs: 30 days
security logs: 90 days
audit records: 365 days recommended
```

Audit retention should follow `config/audit_policy.yaml`:

- minimum: 90 days
- production recommended: 365 days
- deletion requires manual review

### Log Redaction

Redact fields containing:

- token
- password
- secret
- private_key
- credential
- authorization
- api_key

Redaction applies to:

- log metadata
- error metadata
- terminal output summaries
- health details
- trace attributes

## Health Checks

### Health Endpoints

ANUBIS currently has route constants for `/health`, but no HTTP service is present.

Production design should support both:

- CLI health command
- optional local HTTP health endpoint

CLI:

```bash
anubis health
anubis health --json
```

HTTP:

```text
GET /health/live
GET /health/ready
GET /health/startup
GET /health/deep
```

### Liveness

Endpoint:

```text
/health/live
```

Purpose:

Indicates the process is alive and the event loop/runtime can respond.

Checks:

- process responsive
- kill switch state readable
- no fatal startup error

Healthy response:

```json
{
  "status": "ok",
  "service": "anubis",
  "check": "live"
}
```

### Readiness

Endpoint:

```text
/health/ready
```

Purpose:

Indicates ANUBIS can accept work.

Checks:

- configuration loaded
- graph runtime initialized
- observability store writable
- memory system initialized
- sandbox policy loaded
- permissions loaded
- kill switch not active

Readiness states:

```text
ready
degraded
not_ready
```

### Startup

Endpoint:

```text
/health/startup
```

Purpose:

Indicates initialization progress for container orchestration.

Checks:

- config parse complete
- runtime components built
- optional integrations initialized or skipped

### Deep Health

Endpoint:

```text
/health/deep
```

Purpose:

Diagnostic check for operators.

Checks:

- memory read/write probe
- vector retrieval probe
- audit append probe
- log write probe
- sandbox denial/allow probe
- Git availability if workspace is a repo
- Docker availability if Docker integration is enabled
- optional Qdrant connectivity when configured

Deep health may be slower and should not be used for tight liveness probes.

### Health Response Model

```text
HealthResponse
  status
  service
  environment
  version
  timestamp
  uptime_seconds
  checks
```

Check model:

```text
HealthCheck
  name
  status
  duration_ms
  message
  required
  metadata
```

Example:

```json
{
  "status": "degraded",
  "service": "anubis",
  "environment": "production",
  "checks": [
    {
      "name": "memory.vector_store",
      "status": "ok",
      "duration_ms": 2.4,
      "required": true
    },
    {
      "name": "qdrant",
      "status": "skipped",
      "duration_ms": 0.0,
      "required": false,
      "message": "Qdrant is not configured."
    }
  ]
}
```

### Health Security

Public health endpoints should not expose:

- secret values
- filesystem paths beyond configured workspace name
- raw errors with credentials
- full configuration
- prompt or memory contents

Detailed health should require local access or authentication if exposed over a network.

## Alerts

Initial alert rules:

| Alert | Condition | Severity |
| --- | --- | --- |
| Kill switch active | `anubis_kill_switch_active == 1` | critical |
| Sandbox denial spike | repeated denials above policy threshold | high |
| Source modification attempt | any denied source modification attempt | high |
| Graph error rate high | error rate > 1% for 10m | high |
| RAG latency high | retrieval p95 > target for 10m | medium |
| Memory growth high | RSS exceeds configured limit | medium |
| Audit write failure | any failed audit append | critical |
| Health not ready | readiness failing for 5m | high |
| Terminal command denial spike | repeated command denials | medium |

Existing `config/audit_policy.yaml` already defines kill-switch style alert behavior for repeated denials and sandbox escape attempts. Production observability should surface those as metrics and logs.

## Dashboards

### Runtime Overview

Panels:

- graph runs by status
- graph run latency p50/p95/p99
- node latency
- error count
- active tasks
- memory usage
- kill switch status

### Agent and Execution

Panels:

- agent runs by role
- agent latency
- review failures
- command runs by origin
- command failures
- sandbox decisions

### Memory and RAG

Panels:

- memory record count
- retrieval latency
- indexing latency
- cache hit/miss
- result counts
- duplicate chunk detections

### Security and Audit

Panels:

- permission denials
- sandbox denials
- threat findings
- audit append count
- audit integrity failures
- secret redactions

### Git and PR

Panels:

- Git operations by type
- commit creation count
- PR creation count
- PR CI status
- failed CI investigations

## Storage and Export Strategy

### Local Development

Default:

- in-memory collector
- optional JSONL mirror
- local dashboard feed

### Production Local Runtime

Recommended:

- JSONL durable telemetry files
- file rotation
- local health command
- optional Prometheus endpoint
- optional OTLP exporter

### Container Runtime

Recommended:

- write structured logs to stdout
- write audit JSONL to mounted volume
- expose health command for Docker healthcheck
- keep network disabled by default unless exporter is explicitly configured

Docker healthcheck example:

```text
python3 -m anubis health --json
```

### External Export

Optional exporters:

- OpenTelemetry Collector
- Prometheus scrape endpoint
- log shipper reading JSONL/stdout

Network export must be disabled by default and enabled explicitly.

## Configuration

Recommended config file:

```text
config/observability.yaml
```

Suggested shape:

```yaml
observability:
  service_name: anubis
  environment: production
  local_store:
    enabled: true
    path: .anubis/observability
    rotate_mb: 50
    retention_days: 14
  metrics:
    enabled: true
    prometheus_enabled: false
  tracing:
    enabled: true
    sample_success_rate: 1.0
    sample_failures: true
  logs:
    level: info
    jsonl_enabled: true
    stdout_enabled: true
  health:
    cli_enabled: true
    http_enabled: false
  exporters:
    otlp:
      enabled: false
      endpoint: ""
```

This should align with existing `config/logging.yaml` and `config/audit_policy.yaml`, not replace them abruptly.

## Migration Plan

### Phase 1: Canonical Contract

Deliverables:

- define canonical telemetry context
- define common field schema
- map current `core/observability` records to production schema
- map `src/anubis/observability` records to canonical schema or deprecate duplicate schemas

Risk:

```text
Low
```

### Phase 2: Durable Local Sink

Deliverables:

- JSONL sink for logs
- JSONL sink for traces
- JSONL sink for metrics
- durable audit sink
- redaction before write

Risk:

```text
Medium
```

Primary concern:

- persistence changes can expose secrets if redaction is incomplete

### Phase 3: Health Checks

Deliverables:

- CLI health command
- liveness/readiness/startup/deep check model
- Docker healthcheck command
- optional local HTTP endpoint only if/when API service exists

Risk:

```text
Low
```

### Phase 4: Metrics and Dashboards

Deliverables:

- runtime metrics
- sandbox/security metrics
- RAG/memory metrics
- terminal/Git metrics
- local dashboard feed update
- optional Prometheus exposition

Risk:

```text
Medium
```

Primary concern:

- high-cardinality labels from paths/tasks can degrade metrics quality

### Phase 5: OpenTelemetry Export

Deliverables:

- OTLP traces
- OTLP metrics
- OTLP logs if desired
- sampling configuration
- explicit network/export policy

Risk:

```text
Medium
```

Primary concern:

- network export must not violate local-first posture

## Validation Plan

Required tests:

- structured log schema validation
- trace parent/child correlation
- metric snapshot/export validation
- health check status aggregation
- redaction tests
- audit hash-chain integrity tests
- telemetry disabled-mode tests
- no raw secret values in persisted telemetry

Operational validation:

```bash
PYTHONPATH=src:. python3 scripts/run_tests.py
PYTHONPATH=src:. python3 tools/sandbox_tester.py
python3 bootstrap.py "health check observability smoke test" --source observability
```

Acceptance checks:

- failed graph run emits error log, failed span, and error metric
- sandbox denial emits audit record, log event, metric, and trace attribute
- command execution emits stream logs and command metrics
- health command returns ready/degraded/not_ready correctly
- local JSONL files are parseable
- redaction prevents token leakage

## Acceptance Criteria

Production observability is ready when:

- every task has one trace id across graph, agents, memory, sandbox, terminal, and Git
- logs are structured JSON with consistent fields
- metrics cover runtime, agent, memory/RAG, security, terminal, Git, and system health
- health checks distinguish live, ready, startup, and deep diagnostics
- audit records are durable, append-only, and hash-chain verified
- telemetry can run fully local with no network dependency
- optional exporters are disabled by default
- secrets are redacted before persistence or export
- dashboards can show latency, errors, denials, memory growth, and health state

## Final Architecture Contract

```text
Observability Facade
  one API for metrics, tracing, logs, health, and audit correlation

Metrics
  Prometheus-compatible names, low-cardinality labels, local/exportable snapshots

Tracing
  one trace per task, spans for graph nodes, agents, sandbox, memory, commands, Git

Logs
  structured JSONL, redacted, correlated with traces and task ids

Health Checks
  live, ready, startup, and deep checks for CLI and future HTTP runtime

Audit
  separate append-only hash-chained records, correlated but retained independently

Export
  local JSONL by default, optional Prometheus and OpenTelemetry when explicitly enabled
```

This plan turns ANUBIS observability from useful in-memory diagnostics into a production-grade, local-first telemetry system without weakening its security posture.
