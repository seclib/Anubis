# ANUBIS Autonomous Red Team System Design

Date: 2026-06-05

## Goal

Design an Autonomous Red Team system for ANUBIS.

Requirements:

- attack simulation
- sandbox execution
- exploit analysis
- patch recommendation

This is a design artifact only. It does not modify runtime behavior.

## Executive Summary

The Autonomous Red Team should continuously test ANUBIS security assumptions without becoming an unsafe exploit engine.

Its job is to answer:

- can ANUBIS policy be bypassed?
- can sandbox boundaries be escaped?
- can secrets be exposed?
- can plugins abuse permissions?
- can terminal, Git, memory, RAG, or Docker workflows be misused?
- what evidence proves the result?
- what patch or policy change should be recommended?

Operating model:

```text
plan simulation -> execute safely -> capture evidence -> analyze exploitability
  -> recommend patch -> create SOC finding -> require human approval
```

The system should prefer simulations, probes, and policy tests over live exploit execution. Any real command execution must run through the production security layer and isolated runner described in `security_architecture.md`.

## Design Posture

The Red Team system is defensive.

Allowed:

- simulate attacks against local ANUBIS controls
- test sandbox denials
- test permission boundaries
- test path traversal prevention
- test network denial
- test plugin manifest abuse controls
- test audit integrity detection
- generate safe proof-of-concept evidence
- recommend patches and policy changes

Disallowed:

- uncontrolled exploit execution
- targeting third-party systems
- credential theft
- secret exfiltration
- persistence mechanisms
- destructive payloads
- malware generation
- bypassing ANUBIS approval and sandbox controls

## Current Foundation

Relevant local architecture:

- `core/security/PermissionEngine`
- `core/security/SandboxGuard`
- `core/security/ThreatDetector`
- `core/security/KillSwitch`
- `core/security/AuditLogger`
- `tools/sandbox_tester.py`
- `config/sandbox.yaml`
- `config/permissions.yaml`
- `config/production_hardening.yaml`
- `security_architecture.md`
- `soc_design.md`
- `terminal_design.md`
- `observability_plan.md`

Current constraints:

- active graph sandbox is validation/authorization only
- real per-task process isolation is a target architecture, not current active behavior
- audit, telemetry, and incidents are currently planned to become durable
- network is disabled by default in Docker
- source modification is denied by default

Design implication:

The Red Team system must be built in phases. The first version should validate policies and simulate attacks. Real exploit-style execution should wait for the isolated runner, durable audit, and SOC incident store.

## Core Principles

### 1. Safety Envelope First

Every red-team action must have:

- target scope
- maximum permission level
- sandbox profile
- expected effect
- abort condition
- evidence plan
- rollback plan

### 2. Simulated Attack Before Live Probe

Prefer:

```text
policy request -> sandbox decision -> evidence
```

over:

```text
live command -> side effect -> cleanup
```

### 3. No Silent Mutation

Red-team tasks should not mutate source, Git state, memory, config, or secrets unless the simulation explicitly requires a controlled write to scratch or a dedicated test fixture.

### 4. Evidence Is Mandatory

Every finding must include:

- scenario id
- target subsystem
- attempted action
- expected result
- actual result
- audit records
- logs/traces
- sandbox decision
- risk classification

### 5. Recommendations, Not Auto-Patches

The Red Team may recommend patches. It should not apply them automatically.

Patch recommendations should produce:

- policy change
- code change description
- test recommendation
- rollback strategy
- risk level

## Target Architecture

```text
Red Team Campaign Planner
  -> Scenario Catalog
     -> Attack Simulation Engine
        -> Sandbox Execution Harness
           -> Evidence Collector
              -> Exploit Analyzer
                 -> Patch Recommendation Engine
                    -> SOC Integration
                       -> Human Review
```

Supporting stores:

```text
Scenario Store
Campaign Store
Finding Store
Evidence Store
Patch Recommendation Store
```

## Core Components

### Campaign Planner

Responsibilities:

- define scope
- choose scenarios
- set safety envelope
- define expected outcomes
- schedule simulations
- enforce approval requirements

Campaign types:

```text
baseline
pre-release
post-incident
policy-regression
plugin-review
network-review
filesystem-review
memory-review
```

### Scenario Catalog

Responsibilities:

- store approved attack simulations
- classify risk
- define prerequisites
- define safe execution steps
- define expected security response
- define evidence requirements

Scenario fields:

```text
RedTeamScenario
  id
  title
  category
  target_subsystem
  severity_if_successful
  safety_level
  prerequisites
  simulation_steps
  expected_controls
  abort_conditions
  evidence_requirements
```

### Attack Simulation Engine

Responsibilities:

- run scenario steps
- generate structured security requests
- exercise permission and sandbox APIs
- invoke safe terminal probes when allowed
- compare expected vs actual results
- stop on abort conditions

Simulation modes:

```text
policy_only
dry_run
sandbox_probe
isolated_command
fixture_mutation
```

Default:

```text
policy_only
```

### Sandbox Execution Harness

Responsibilities:

- route every execution through the security kernel
- select sandbox profile
- run only approved safe probes
- stream output through terminal architecture
- enforce timeouts and resource limits
- block uncontrolled network and filesystem access

Required controls:

- no host filesystem access
- no raw network
- no source modification by default
- no secret access
- no Docker daemon access unless campaign explicitly approves Docker test
- kill switch respected

### Evidence Collector

Responsibilities:

- collect audit records
- collect logs
- collect traces
- collect metrics
- collect sandbox decisions
- collect terminal output summaries
- collect Git diff if controlled fixture mutation occurs
- redact secrets

Evidence references:

```text
audit_record_id
trace_id
span_id
command_id
log_record_id
metric_window
sandbox_decision_id
incident_id
```

### Exploit Analyzer

Responsibilities:

- classify whether a scenario was blocked, partially successful, or successful
- determine likely root cause
- estimate blast radius
- map result to security control failure
- assign severity
- generate SOC finding

Result classifications:

```text
blocked
blocked_with_warning
partial_bypass
control_gap
successful_bypass
inconclusive
```

### Patch Recommendation Engine

Responsibilities:

- recommend code, config, test, or documentation changes
- avoid applying changes automatically
- produce migration and rollback notes
- link recommendation to finding evidence

Recommendation types:

```text
policy_change
code_change
test_addition
config_change
documentation_clarification
operational_playbook
dependency_change
```

### SOC Integration

Responsibilities:

- create alerts for serious findings
- create incidents for high/critical successful or partial bypasses
- link red-team campaign evidence
- update incident timelines
- recommend containment

Integration points:

- `soc_design.md` alert model
- `soc_design.md` incident model
- `observability_plan.md` metrics/logs/traces
- `security_architecture.md` audit and kill switch

## Attack Simulation Categories

### Permission Boundary Tests

Purpose:

Validate deny-by-default permission behavior.

Examples:

- actor requests permission not granted
- explicit deny conflicts with allow
- wildcard grant appears in config
- plugin asks for undeclared capability
- task asks for forbidden permission

Expected result:

- denied
- audit record created
- detection rule may fire for repeated attempts

### Sandbox Escape Tests

Purpose:

Validate sandbox invariants.

Examples:

- non-sandbox filesystem mode requested
- source modification permission requested outside approved workflow
- raw network mode requested
- unsupported network mode requested
- Docker access requested without approval

Expected result:

- denied
- audit record created
- SOC alert/incident for critical attempts
- kill switch when configured

### Filesystem Isolation Tests

Purpose:

Validate workspace/scratch/host boundaries.

Examples:

- path traversal attempt
- symlink escape attempt
- absolute host path access
- protected path read attempt
- write outside approved scratch path
- `.git` internals access outside Git service

Expected result:

- denied or blocked before execution
- evidence includes canonical path decision

### Network Isolation Tests

Purpose:

Validate disabled-by-default network posture.

Examples:

- network request without `network.explicit`
- request to non-allowlisted host
- request with secret-bearing payload classification
- raw socket request
- package install without approval

Expected result:

- denied or approval-required
- no network egress in default profile

### Secret Exposure Tests

Purpose:

Validate secret handling and redaction.

Examples:

- raw secret memory write
- terminal output containing token-like value
- log metadata with secret-like key
- vault value requested instead of reference
- RAG index attempts to ingest secret-like file

Expected result:

- raw value blocked or redacted
- secret access audited
- finding created if exposure reaches persisted evidence

### Plugin Abuse Tests

Purpose:

Validate plugin lifecycle and manifest enforcement.

Examples:

- plugin action before start
- undeclared permission request
- dynamic import attempt
- symbolic entrypoint mismatch
- plugin requests network and secret access sequence

Expected result:

- denied
- plugin alert or incident if abuse pattern is detected

### Git Workflow Abuse Tests

Purpose:

Validate Git safety gates.

Examples:

- force push request
- commit with mixed user/ANUBIS changes
- PR creation with failed tests
- branch deletion with unmerged work
- reset operation outside approved rollback

Expected result:

- approval required or denied
- incident for high-risk denied publication attempts

### Memory and RAG Abuse Tests

Purpose:

Validate memory isolation and RAG safety.

Examples:

- cross-workspace memory retrieval
- duplicate indexing spike
- retrieval of vault memory raw values
- indexing ignored/private files
- unsafe context expansion beyond task scope

Expected result:

- denied or restricted
- memory/RAG finding with evidence

### Audit Integrity Tests

Purpose:

Validate tamper detection.

Examples:

- sequence gap
- hash-chain mismatch
- timestamp regression
- missing security decision event
- audit append failure simulation

Expected result:

- critical finding
- SOC incident
- kill switch for audit integrity failure

## Sandbox Execution Model

### Execution Levels

#### Level 0: Static Review

No execution.

Used for:

- config review
- manifest review
- code pattern review
- policy diff review

#### Level 1: Policy Simulation

Constructs requests and evaluates security decisions.

Used for:

- permission tests
- sandbox request tests
- approval gate tests

#### Level 2: Dry-Run Probe

Runs non-mutating checks in an isolated or validation-only environment.

Used for:

- path canonicalization
- network policy dry-run
- Git status/diff checks

#### Level 3: Isolated Fixture Execution

Runs safe probes against synthetic fixtures in scratch/worktree.

Used for:

- symlink fixture tests
- controlled file write denial tests
- plugin fixture tests

#### Level 4: Production-Like Isolated Runner

Runs approved probes in a production sandbox profile.

Use only after:

- isolated runner exists
- durable audit exists
- SOC incident store exists
- human approval granted

### Execution Guardrails

Every run must enforce:

- timeout
- memory limit
- PID limit
- no raw network
- no host filesystem
- scratch-only writes unless approved
- redacted output
- audit logging
- kill switch check before each step

## Exploit Analysis

### Finding Model

```text
RedTeamFinding
  id
  campaign_id
  scenario_id
  title
  severity
  status
  result
  target_subsystem
  expected_result
  actual_result
  exploitability
  blast_radius
  evidence_refs
  recommended_actions
```

### Exploitability Levels

```text
none
  Control worked as expected.

theoretical
  Design gap exists, but no executable path demonstrated.

limited
  Partial bypass in fixture or narrow scope.

practical
  Bypass demonstrated against local control with meaningful impact.

critical
  Bypass could expose secrets, mutate protected source, escape sandbox, or disable audit.
```

### Severity Mapping

| Result | Exploitability | Severity |
| --- | --- | --- |
| blocked | none | informational |
| blocked_with_warning | theoretical | low |
| control_gap | theoretical | medium |
| partial_bypass | limited | high |
| successful_bypass | practical | critical |
| successful_bypass | critical | critical |

### Root Cause Categories

- missing permission check
- overly broad permission grant
- sandbox invariant gap
- path canonicalization gap
- network policy gap
- redaction gap
- audit persistence gap
- plugin manifest validation gap
- Git approval gap
- memory isolation gap
- configuration drift
- documentation/runtime mismatch

## Patch Recommendation

### Recommendation Model

```text
PatchRecommendation
  id
  finding_id
  type
  title
  rationale
  affected_files
  proposed_change
  tests_to_add
  migration_notes
  rollback_strategy
  risk_level
  requires_human_approval
```

### Recommendation Rules

Recommendations must:

- cite finding evidence
- identify exact control gap
- preserve current functionality
- include regression test
- include rollback strategy
- avoid automatic patch application

Recommendations must not:

- include weaponized exploit payloads
- expose secret values
- weaken sandbox policy
- bypass approval flows

### Recommendation Examples

Policy change:

```text
Add explicit deny for plugin.dynamic_import to authoritative permission config.
```

Code change:

```text
Canonicalize symlink targets before filesystem zone evaluation.
```

Test addition:

```text
Add regression test for path traversal through nested symlink fixture.
```

Documentation clarification:

```text
Clarify that graph sandbox is authorization/validation until isolated runner is enabled.
```

## Campaign Workflow

### 1. Scope Campaign

Define:

- target subsystem
- scenarios
- execution level
- allowed profiles
- maximum severity
- evidence retention
- approval requirements

### 2. Preflight

Check:

- security config loaded
- sandbox policy available
- audit logging available
- SOC store available
- kill switch inactive
- workspace clean or fixture-only campaign

### 3. Run Scenarios

For each scenario:

- create trace
- execute steps
- collect evidence
- compare expected vs actual
- stop on abort condition

### 4. Analyze

Produce:

- result classification
- exploitability rating
- severity
- root cause
- blast radius

### 5. Report

Produce:

- campaign summary
- findings
- evidence index
- patch recommendations
- SOC alerts/incidents

### 6. Human Review

Human decides:

- accept finding
- mark false positive
- request more evidence
- approve patch work
- suppress rule
- open cleanup task

## Integration With SOC

Red Team findings should feed SOC.

Mapping:

```text
informational/low finding -> SOC alert optional
medium finding -> SOC alert
high finding -> SOC alert + incident
critical finding -> SOC incident + possible kill switch
```

SOC timeline events:

- red_team_campaign_started
- red_team_scenario_executed
- red_team_finding_created
- red_team_patch_recommended
- red_team_campaign_completed

## Metrics

Red Team metrics:

| Metric | Type | Labels |
| --- | --- | --- |
| `anubis_redteam_campaigns_total` | counter | `type`, `status` |
| `anubis_redteam_scenarios_total` | counter | `category`, `result` |
| `anubis_redteam_findings_total` | counter | `severity`, `result` |
| `anubis_redteam_execution_duration_ms` | histogram | `scenario_category` |
| `anubis_redteam_patch_recommendations_total` | counter | `type`, `risk_level` |
| `anubis_redteam_false_positives_total` | counter | `scenario_category` |

## Storage

Recommended local store:

```text
.anubis/red_team/
  campaigns.jsonl
  scenarios.jsonl
  findings.jsonl
  evidence_index.jsonl
  recommendations.jsonl
```

Properties:

- local-first
- redacted before write
- append-only campaign events
- evidence-linked
- exportable for audits

Future option:

- SQLite for searchable historical campaigns

## Permissions

Red Team permissions:

```text
redteam.campaign.read
redteam.campaign.write
redteam.scenario.read
redteam.scenario.execute
redteam.finding.read
redteam.finding.write
redteam.recommendation.write
redteam.fixture.write
```

Restricted permissions:

```text
redteam.live_probe.execute
redteam.network_probe.execute
redteam.docker_probe.execute
redteam.patch.apply
```

Default:

- `redteam.patch.apply` denied
- network probes disabled
- live probes approval-required
- fixture writes limited to scratch/worktree

## Workspace Integration

### Left Rail

Optional Red Team tab:

- campaigns
- scenarios
- findings
- recommendations

### Center Panel

Campaign detail:

- scope
- scenario list
- execution progress
- evidence
- findings
- recommendations

### Bottom Terminal

Red Team command tab:

- safe probe output
- sandbox decisions
- test fixture commands
- audit verification commands

### Right Rail

Security context:

- active campaign
- current scenario
- sandbox profile
- SOC alerts/incidents
- kill switch state

## Rollout Plan

### Phase 1: Scenario Catalog

Deliverables:

- approved scenario schema
- initial scenario catalog
- safety classification
- expected control mapping

Risk:

```text
Low
```

### Phase 2: Policy Simulation Engine

Deliverables:

- permission simulation
- sandbox request simulation
- expected/actual comparator
- evidence collector

Risk:

```text
Low-Medium
```

### Phase 3: Finding and Recommendation Engine

Deliverables:

- finding model
- exploitability classification
- patch recommendation model
- report generation

Risk:

```text
Medium
```

### Phase 4: SOC Integration

Deliverables:

- alert creation
- incident creation
- SOC timeline events
- red-team metrics

Risk:

```text
Medium
```

### Phase 5: Isolated Fixture Execution

Deliverables:

- scratch/worktree fixture runner
- path traversal fixture tests
- plugin fixture tests
- terminal streaming integration

Risk:

```text
Medium-High
```

### Phase 6: Production-Like Runner Campaigns

Deliverables:

- isolated runner support
- resource-limited live probes
- network-disabled execution
- optional approved network probes

Risk:

```text
High
```

Primary concern:

- live probes must never outpace the security layer.

## Validation Plan

Required validation:

- scenario safety schema validation
- policy-only simulation produces no filesystem changes
- sandbox escape scenario is denied
- raw network scenario is denied
- source modification scenario is denied
- secret exposure scenario redacts evidence
- audit integrity scenario creates critical finding
- finding links to evidence refs
- recommendation includes rollback strategy
- high finding creates SOC incident
- kill switch is respected before each scenario step

Recommended smoke campaign:

```text
Campaign: baseline-security
Execution level: policy_only
Scenarios:
- permission_missing_grant
- sandbox_source_modify_denied
- sandbox_host_filesystem_denied
- network_raw_denied
- plugin_dynamic_import_denied
- raw_secret_memory_denied
```

## Acceptance Criteria

The Autonomous Red Team system is ready when:

- approved scenarios can run in policy-only mode without side effects
- sandbox execution is routed through the production security layer
- every scenario produces evidence-linked results
- exploit analysis classifies blocked, partial, and successful bypasses
- patch recommendations are generated but not applied automatically
- high and critical findings integrate with SOC incidents
- secret-like evidence is redacted
- network and host filesystem probes are denied by default
- live probes require isolated runner and human approval
- campaign reports are durable and auditable

## Final Architecture Contract

```text
Campaign Planner
  scopes defensive campaigns and safety envelopes

Scenario Catalog
  stores approved simulations with expected controls and abort conditions

Attack Simulation Engine
  runs policy simulations and safe sandbox probes

Sandbox Execution Harness
  enforces security kernel, isolation profile, timeout, resource, and audit rules

Evidence Collector
  captures redacted logs, traces, audit records, sandbox decisions, and command output

Exploit Analyzer
  classifies results, exploitability, root cause, severity, and blast radius

Patch Recommendation Engine
  proposes code/config/test/docs changes for human review

SOC Integration
  creates alerts, incidents, and timeline events for serious findings
```

This design gives ANUBIS an autonomous defensive red-team loop while preserving the central safety constraint: simulations and recommendations are automated; exploit execution and patch application remain controlled, sandboxed, and human-approved.
