# ANUBIS AI SOC Architecture

Date: 2026-06-05

## Goal

Design the AI Security Operations Center architecture for ANUBIS.

Requirements:

- monitoring
- anomaly detection
- incident tracking
- alerting

This is a design artifact only. It does not modify runtime behavior.

## Executive Summary

ANUBIS should treat security operations as a first-class runtime capability, not as a passive dashboard.

The AI SOC should continuously monitor:

- permission decisions
- sandbox decisions
- terminal commands
- Git operations
- network attempts
- filesystem writes
- plugin execution
- memory and RAG activity
- audit integrity
- health and performance degradation

It should detect anomalies, create incidents, alert humans, and recommend safe response actions while preserving ANUBIS's local-first and human-controlled posture.

Target operating model:

```text
observe -> detect -> triage -> contain -> investigate -> resolve -> learn
```

## Current State

Relevant existing pieces:

- `core/security/ThreatDetector`
- `core/security/KillSwitch`
- `core/security/AuditLogger`
- `core/security/SecurityKernel`
- `src/anubis/safety.py`
- `src/anubis/audit.py`
- `config/audit_policy.yaml`
- `config/production_hardening.yaml`
- `security_architecture.md`
- `observability_plan.md`
- `terminal_design.md`

Current strengths:

- audit-based threat detection exists
- repeated denials can trigger kill switch
- sandbox escape attempts can trigger kill switch
- security policies already define important alert classes
- observability plan defines metrics, traces, logs, health, alerts, and dashboards

Current gaps:

- no durable incident store
- no SOC queue
- no formal severity model
- no alert routing
- no investigation workflow
- no detection rule catalog
- no analyst-facing security timeline
- no durable telemetry store yet

## SOC Principles

### 1. Evidence First

Every alert and incident must link to evidence:

- audit records
- logs
- traces
- terminal commands
- diff or Git events
- sandbox decisions
- health state

### 2. Human-Controlled Response

The SOC may recommend containment, but destructive or broad actions require approval.

Allowed automatic response:

- raise alert
- create incident
- activate kill switch only for critical policy-defined events
- block action already denied by policy
- preserve evidence

Not automatic by default:

- delete files
- revert commits
- rotate credentials
- push Git changes
- disable plugins globally except through configured containment policy

### 3. Local-First Operations

The SOC must function without network access.

Default:

- local telemetry
- local incident store
- local alerts
- local dashboard

Optional:

- webhook export
- SIEM export
- email/chat alerting
- OpenTelemetry export

### 4. Deterministic Detection Before AI Judgment

Deterministic rules should fire first. AI-assisted triage can enrich, summarize, and recommend actions after evidence is collected.

### 5. No Secret Leakage

SOC evidence must use the same redaction rules as production observability and security layers.

## Target Architecture

```text
Telemetry Sources
  -> Signal Ingestion
     -> Normalization and Redaction
        -> Detection Engine
           -> Alert Manager
              -> Incident Manager
                 -> Triage Assistant
                    -> Response Orchestrator
                       -> Audit and Case Timeline
```

Supporting stores:

```text
Telemetry Store
Detection Rule Store
Alert Store
Incident Store
Evidence Store
SOC Memory
```

## Core Components

### Signal Ingestion

Responsibilities:

- subscribe to logs, metrics, traces, audit records, health checks, and terminal events
- normalize events into a common security event model
- preserve correlation ids
- redact secrets
- route events to detection engine

Sources:

- audit logger
- structured logger
- metrics collector
- tracer
- terminal execution log
- Git service
- memory service
- RAG service
- plugin manager
- health check service
- Docker/runtime probes

### Security Event Model

```text
SecurityEvent
  id
  timestamp
  source
  event_type
  actor
  action
  resource
  allowed
  severity_hint
  trace_id
  span_id
  task_id
  command_id
  workspace_id
  metadata
  evidence_refs
```

Event sources:

```text
audit
log
metric
trace
terminal
git
memory
rag
plugin
health
docker
```

### Detection Engine

Responsibilities:

- run deterministic rules
- run statistical anomaly checks
- run sequence/correlation rules
- produce findings
- assign severity
- link evidence
- recommend response

Detection families:

1. Policy violation detection
2. Behavioral anomaly detection
3. Resource anomaly detection
4. Integrity detection
5. Secret exposure detection
6. Network anomaly detection
7. Plugin abuse detection
8. Git risk detection
9. Memory/RAG risk detection

### Alert Manager

Responsibilities:

- convert findings into alerts
- deduplicate alerts
- group related alerts
- suppress noisy repeats
- escalate severity
- route notifications
- track alert status

Alert states:

```text
new
acknowledged
linked_to_incident
suppressed
resolved
false_positive
```

### Incident Manager

Responsibilities:

- create incidents from alerts
- maintain incident lifecycle
- link evidence
- assign severity
- track owner/status
- record timeline
- record response actions
- produce post-incident summary

Incident states:

```text
open
triaging
contained
investigating
monitoring
resolved
closed
```

### Triage Assistant

Responsibilities:

- summarize evidence
- identify likely root cause
- explain blast radius
- recommend containment
- propose next investigation steps
- draft incident updates
- produce postmortem summary

Guardrail:

The triage assistant may not invent evidence. Every claim must reference a concrete event, log, trace, metric, or audit record.

### Response Orchestrator

Responsibilities:

- execute approved response actions
- invoke kill switch when policy requires
- disable task/plugin/session by policy
- preserve evidence
- open follow-up task
- request user approval for elevated actions

Response actions:

```text
preserve_evidence
activate_kill_switch
deny_action
pause_task
disable_plugin
block_network_profile
request_secret_rotation
open_investigation_task
generate_report
```

## Monitoring

### Runtime Monitoring

Monitor:

- graph run success/failure
- node failures
- agent failures
- execution duration
- terminal command duration
- memory growth
- health status
- Docker resource pressure

Signals:

- `anubis_graph_runs_total`
- `anubis_graph_run_duration_ms`
- `anubis_command_runs_total`
- `anubis_process_memory_rss_bytes`
- `/health/ready`
- `/health/deep`

### Security Monitoring

Monitor:

- permission denials
- sandbox denials
- kill switch status
- threat findings
- audit append failures
- audit integrity failures
- secret redactions
- raw network attempts
- filesystem escape attempts

Signals:

- `anubis_sandbox_decisions_total`
- `anubis_permission_decisions_total`
- `anubis_threat_findings_total`
- `anubis_kill_switch_active`
- audit records

### Agent Monitoring

Monitor:

- repeated failed agent runs
- planner requests for forbidden capabilities
- executor attempts to cross policy boundaries
- reviewer missing traceability
- abnormal context/token usage
- repeated retries

Relevant roles:

- Planner
- Executor
- Reviewer

### Terminal Monitoring

Monitor:

- destructive command attempts
- command denial spikes
- network tools
- package installation
- Docker daemon access
- writes outside workspace
- commands containing secret-like values

Signals:

- terminal command logs
- command risk class
- sandbox decision
- approval decision
- output redaction events

### Git Monitoring

Monitor:

- force push attempts
- branch deletion
- reset operations
- commits with user-authored changes staged accidentally
- PR creation with failed tests
- changes to security-sensitive files

High-risk files:

- security config
- permissions config
- sandbox config
- CI workflows
- Dockerfile
- dependency manifests
- secrets policy

### Memory and RAG Monitoring

Monitor:

- raw secret storage attempts
- vault value exposure
- cross-workspace retrieval
- unexpected collection writes
- duplicate indexing spikes
- retrieval of sensitive files
- RAG latency anomalies

## Anomaly Detection

### Detection Rule Types

#### Threshold Rules

Example:

```text
3 sandbox denials by same actor in 10 minutes
```

Use for:

- repeated denials
- command failures
- redaction spikes
- health failures

#### Point-in-Time Rules

Example:

```text
source modification denied
```

Use for:

- sandbox escape attempts
- audit write failure
- kill switch activation
- raw network attempt

#### Sequence Rules

Example:

```text
plugin start -> network request -> secret access attempt
```

Use for:

- plugin abuse
- staged exfiltration behavior
- suspicious Git publication flow

#### Baseline Rules

Example:

```text
RAG retrieval latency is 5x normal p95
```

Use for:

- resource anomalies
- performance degradation
- memory growth
- unexpected task duration

#### Integrity Rules

Example:

```text
audit hash chain verification failed
```

Use for:

- audit tampering
- missing events
- timestamp regression
- sequence gaps

### Initial Detection Catalog

| Rule | Condition | Severity | Default Response |
| --- | --- | --- | --- |
| Sandbox escape attempt | denied non-sandbox filesystem or source modification | critical | kill switch, incident |
| Repeated denials | same actor denied >= 3 times | high/critical | incident, maybe kill switch |
| Raw network attempt | request for `network.raw` | critical | deny, incident |
| Audit write failure | audit append fails | critical | kill switch, incident |
| Audit integrity failure | hash-chain invalid | critical | kill switch, incident |
| Secret storage attempt | raw secret written to memory/repo/log | high | deny, incident |
| Secret redaction spike | redactions exceed baseline | medium | alert |
| Plugin dynamic import | plugin attempts dynamic import/runtime code loading | critical | disable plugin, incident |
| Destructive terminal command | delete/reset/chmod outside approved flow | high | approval or deny, incident if denied |
| Docker daemon access | Docker access without approval | high | deny, alert |
| Network to unknown host | explicit network request to non-allowlisted host | high | deny, alert |
| Health not ready | readiness failing for 5 minutes | high | alert |
| Memory growth | RSS exceeds threshold | medium | alert |
| RAG latency anomaly | retrieval p95 above threshold | medium | alert |
| PR with failed tests | PR creation attempted with failed tests | medium | warning/alert |
| Security config changed | changes to policy files | high | require review |

### Severity Model

```text
critical
  Active or attempted policy breach, audit failure, kill switch condition.

high
  Security-sensitive blocked action, suspicious sequence, significant degradation.

medium
  Abnormal behavior requiring review, not immediate containment.

low
  Informational drift, benign anomaly, weak signal.
```

## Incident Tracking

### Incident Model

```text
Incident
  id
  title
  severity
  status
  created_at
  updated_at
  owner
  source_alerts
  affected_tasks
  affected_actors
  affected_resources
  trace_ids
  evidence_refs
  timeline
  containment_actions
  resolution
  lessons
```

### Incident Lifecycle

```text
open
  -> triaging
     -> contained
        -> investigating
           -> monitoring
              -> resolved
                 -> closed
```

Emergency path:

```text
open -> contained -> investigating
```

False positive path:

```text
open -> triaging -> false_positive -> closed
```

### Incident Timeline

Every incident should maintain a timeline:

```text
IncidentTimelineEvent
  timestamp
  actor
  event_type
  summary
  evidence_ref
  action_taken
```

Timeline event types:

- alert_created
- incident_created
- evidence_attached
- user_acknowledged
- kill_switch_triggered
- containment_applied
- investigation_note
- status_changed
- resolution_added
- incident_closed

### Evidence References

Evidence references should point to durable records:

- audit record id
- log record id
- trace id/span id
- command id
- metric window
- health check id
- Git diff id
- memory record id

Evidence should not duplicate raw secret-bearing data.

## Alerting

### Alert Model

```text
Alert
  id
  rule_id
  title
  severity
  status
  created_at
  actor
  resource
  trace_id
  task_id
  evidence_refs
  recommended_action
```

### Alert Routing

Default local routing:

- SOC dashboard
- workspace right-rail security panel
- terminal notification
- structured log
- local alert JSONL

Optional routing:

- webhook
- email
- Slack/Teams
- SIEM
- OpenTelemetry event

Network alert routing is disabled by default and must be explicitly configured.

### Alert Deduplication

Deduplicate by:

- rule id
- actor
- resource
- task id
- time window

Example:

```text
same actor repeated denials within 10 minutes -> one alert with count
```

### Alert Suppression

Suppression requires:

- rule id
- reason
- expiration
- actor who suppressed
- audit record

Suppression must not hide critical audit integrity failures or kill switch activation.

## SOC Dashboard

### Overview

Panels:

- active incidents by severity
- new alerts
- kill switch state
- health readiness
- sandbox denials
- permission denials
- secret redactions
- audit integrity status

### Detection View

Panels:

- detection rules
- last triggered time
- firing count
- false positive count
- enabled/disabled state
- rule severity

### Incident Queue

Columns:

- incident id
- severity
- status
- title
- affected actor
- affected task
- created time
- owner

### Investigation View

Sections:

- summary
- timeline
- evidence
- related traces
- related commands
- affected files/resources
- recommended actions
- analyst notes

### Alert Detail

Sections:

- rule explanation
- matched condition
- evidence
- severity rationale
- related alerts
- convert/link to incident
- suppress/escalate controls

## AI Triage

### Inputs

The triage assistant may use:

- normalized security events
- incident timeline
- audit records
- logs
- traces
- command output summaries
- Git diffs
- health checks
- detection rule metadata

### Outputs

The triage assistant may produce:

- concise incident summary
- severity rationale
- likely root cause
- blast radius
- recommended containment
- recommended investigation steps
- post-incident report draft

### Guardrails

The assistant must:

- cite evidence refs
- distinguish facts from inference
- avoid hidden chain-of-thought
- avoid exposing secrets
- not downgrade critical policy events without human approval
- not close incidents automatically by default

## Response Playbooks

### Sandbox Escape Attempt

Trigger:

- non-sandbox filesystem request
- source modification attempt outside approved flow

Actions:

1. Trigger kill switch.
2. Create critical incident.
3. Preserve audit/log/trace evidence.
4. Identify actor and task.
5. Block further mutating actions.
6. Generate investigation summary.
7. Require human review to resume.

### Repeated Denials

Trigger:

- same actor denied above threshold.

Actions:

1. Create high or critical alert.
2. Group denial evidence.
3. Identify requested permissions.
4. Determine whether planner is over-requesting.
5. Recommend plan correction or actor disablement.

### Secret Exposure Attempt

Trigger:

- raw secret write, secret-like terminal output, or secret storage attempt.

Actions:

1. Redact evidence.
2. Create high incident.
3. Identify source and destination.
4. Block storage/export.
5. Recommend credential rotation if exposure left trusted boundary.

### Plugin Abuse

Trigger:

- dynamic import attempt
- undeclared permission request
- suspicious sequence involving plugin + network + secrets

Actions:

1. Disable plugin for session.
2. Create incident.
3. Preserve plugin manifest and execution evidence.
4. Review requested capabilities.
5. Require explicit re-enable.

### Audit Integrity Failure

Trigger:

- hash-chain mismatch
- sequence gap
- audit append failure

Actions:

1. Trigger kill switch.
2. Create critical incident.
3. Preserve available audit files.
4. Stop mutating operations.
5. Require manual forensic review.

### Network Exfiltration Suspicion

Trigger:

- network request to unapproved host
- secret-bearing request
- unusual volume of outbound calls

Actions:

1. Deny request.
2. Create high incident.
3. Preserve request metadata.
4. Identify data classification.
5. Recommend network policy update or task correction.

## Data Storage

Recommended local SOC store:

```text
.anubis/soc/
  alerts.jsonl
  incidents.jsonl
  incident_timeline.jsonl
  detections.jsonl
  evidence_index.jsonl
```

Properties:

- append-only event log
- redacted before write
- linked by ids
- exportable
- works offline

Future option:

- SQLite for indexed search and incident workflow queries

## Detection Rules

Recommended config:

```text
config/soc_rules.yaml
```

Example:

```yaml
rules:
  - id: sandbox_escape_attempt
    severity: critical
    enabled: true
    type: point_in_time
    match:
      event_type: sandbox.denied
      reason_contains:
        - filesystem must be sandbox_only
        - source modification is not allowed
    response:
      - create_incident
      - trigger_kill_switch
```

Rule fields:

- id
- title
- severity
- enabled
- type
- condition
- window
- threshold
- response
- suppression_allowed

## Metrics

SOC metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_soc_alerts_total` | counter | `rule_id`, `severity` |
| `anubis_soc_incidents_total` | counter | `severity`, `status` |
| `anubis_soc_open_incidents` | gauge | `severity` |
| `anubis_soc_detection_duration_ms` | histogram | `rule_type` |
| `anubis_soc_false_positives_total` | counter | `rule_id` |
| `anubis_soc_mean_time_to_ack_ms` | histogram | `severity` |
| `anubis_soc_mean_time_to_resolve_ms` | histogram | `severity` |

## Health Checks

SOC health checks:

- signal ingestion active
- detection engine active
- alert store writable
- incident store writable
- audit source readable
- rule config valid
- redaction active
- kill switch state readable

Health states:

```text
ok
degraded
not_ready
```

Critical failure:

- audit source unavailable
- incident store not writable
- detection rules invalid

## Permissions

SOC permissions:

```text
soc.alert.read
soc.alert.write
soc.incident.read
soc.incident.write
soc.rule.read
soc.rule.write
soc.response.execute
soc.evidence.read
```

Restricted actions:

- suppress alert
- close incident
- disable rule
- trigger kill switch manually
- disable plugin

These require explicit user or security-operator approval.

## Integration With Workspace

### Left Rail

Optional SOC tab:

- alerts
- incidents
- detection rules
- security timeline

### Center Panel

Incident investigation surface:

- incident summary
- timeline
- evidence
- triage assistant recommendations
- response actions

### Bottom Terminal

SOC command/evidence tab:

- security command output
- forensic commands
- health checks
- audit verification

### Right Rail

Security status:

- active alerts
- kill switch state
- current task risk
- sandbox decision stream
- memory/security references

## Rollout Plan

### Phase 1: SOC Event Model

Deliverables:

- `SecurityEvent` schema
- event normalization map
- evidence reference model
- redaction requirement

Risk:

```text
Low
```

### Phase 2: Detection Rules

Deliverables:

- deterministic detection engine
- initial rule catalog
- repeated denial detection
- sandbox escape detection
- audit integrity detection

Risk:

```text
Medium
```

### Phase 3: Alerts

Deliverables:

- alert model
- deduplication
- alert states
- local alert store
- dashboard feed

Risk:

```text
Medium
```

### Phase 4: Incidents

Deliverables:

- incident model
- incident lifecycle
- timeline
- evidence linking
- analyst notes

Risk:

```text
Medium
```

### Phase 5: AI Triage

Deliverables:

- evidence-grounded summaries
- severity rationale
- response recommendations
- post-incident report draft

Risk:

```text
Medium-High
```

Primary concern:

- AI triage must not invent facts or hide evidence gaps.

### Phase 6: Response Orchestration

Deliverables:

- response playbooks
- approval gates
- plugin/session containment
- kill switch integration

Risk:

```text
High
```

Primary concern:

- response actions can disrupt legitimate work if overly broad.

## Validation Plan

Required tests:

- alert creation from sandbox denial
- incident creation from critical alert
- repeated denial grouping
- alert deduplication
- alert suppression audit
- audit integrity failure incident
- secret redaction in evidence
- AI triage cites evidence refs
- kill switch incident path
- plugin abuse playbook
- network denial playbook

SOC simulation scenarios:

```text
source.modify denied
filesystem.host denied
network.raw denied
plugin.dynamic_import denied
audit hash mismatch
secret-like terminal output
repeated executor denials
health readiness failure
```

## Acceptance Criteria

The AI SOC architecture is ready when:

- security events are normalized across audit, logs, traces, metrics, terminal, Git, plugins, and memory
- deterministic detection rules produce evidence-linked alerts
- alerts are deduplicated, routed, and stateful
- critical alerts create incidents
- incidents have lifecycle, owner, timeline, evidence, and resolution fields
- AI triage summarizes evidence without inventing facts
- response playbooks preserve evidence and require approval for disruptive action
- kill switch events create critical incidents automatically
- SOC runs locally without network dependency
- all persisted SOC evidence is redacted

## Final Architecture Contract

```text
Monitoring
  ingest audit, logs, metrics, traces, health, terminal, Git, memory, plugin signals

Anomaly Detection
  deterministic rules first, statistical baselines second, AI triage only after evidence

Alerting
  evidence-linked, deduplicated, routed locally by default, export optional

Incident Tracking
  durable cases with severity, lifecycle, owner, timeline, evidence, and resolution

Response
  preserve evidence, contain safely, use kill switch for critical policy events,
  require human approval for disruptive action
```

This SOC design turns ANUBIS security from a set of runtime checks into an operational security loop: continuous monitoring, evidence-grounded detection, incident response, and controlled recovery.
