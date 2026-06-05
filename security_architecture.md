# ANUBIS Production Security Architecture

Date: 2026-06-05

## Goal

Design the production security layer for ANUBIS.

Requirements:

- sandboxing
- filesystem isolation
- network isolation
- permission system

This is a design artifact only. It does not modify runtime behavior.

## Executive Summary

ANUBIS has a strong local-first security posture today:

- deny-by-default permissions
- sandbox guard for execution requests
- hardened Docker defaults
- no default network
- no runtime third-party dependencies
- append-only audit concepts
- kill switch for critical security events

The main production gap is not intent. It is isolation strength.

Current active graph sandboxing is an authorization and validation boundary. It does not yet provide per-task OS process isolation. Production security must therefore introduce a layered model:

```text
Policy authorization
  -> sandbox decision
     -> isolated runner
        -> filesystem boundary
           -> network boundary
              -> audit and kill switch
```

## Current State

Relevant existing components:

- `core/security/PermissionEngine`
- `core/security/SandboxGuard`
- `core/security/AuditLogger`
- `core/security/KillSwitch`
- `core/security/ThreatDetector`
- `core/security/SecurityKernel`
- `src/anubis/sandbox.py`
- `src/anubis/safety.py`
- `config/sandbox.yaml`
- `config/permissions.yaml`
- `config/production_hardening.yaml`
- `docs/production_hardening.md`
- `docs/docker_runtime_security.md`
- `docs/security_model.md`

Current constraints:

- default Docker service disables network
- container root filesystem is read-only
- container runs as non-root
- Linux capabilities are dropped
- no-new-privileges is enabled
- `/tmp` is mounted as constrained tmpfs
- current graph execution does not spawn arbitrary OS commands

Current production blockers:

- sandbox semantics can be overread as process isolation
- policies in config are not necessarily authoritative runtime inputs
- audit records are in-memory
- no dedicated per-task isolated runner exists
- duplicate security/sandbox implementations exist across `core/` and `src/anubis/`

## Threat Model

### Assets

Protected assets:

- repository source code
- user-authored uncommitted changes
- secrets and vault references
- memory records
- audit records
- Git credentials
- local filesystem outside workspace
- network credentials
- Docker daemon
- production deployment controls

### Threats

ANUBIS must defend against:

- unauthorized source modification
- host filesystem access
- raw network access
- sandbox escape attempts
- plugin abuse
- generated code execution
- runtime code injection
- destructive shell commands
- secret exfiltration
- prompt/task attempts to bypass policy
- audit tampering
- privilege escalation through Docker or OS facilities

### Non-Goals

Initial production security does not need to support:

- automatic production deployment
- autonomous merge to protected branches
- arbitrary plugin code loading
- remote multi-user execution
- privileged Docker builds without approval
- unrestricted web browsing

## Security Principles

### 1. Deny by Default

Every action is denied unless explicitly allowed.

Required:

- no wildcard permissions
- explicit deny overrides allow
- permission checks before sandbox execution
- sandbox checks before runner execution
- audit every allow and deny

### 2. Least Authority

Agents, plugins, terminal commands, Git actions, and memory operations receive only the permissions required for the current task.

### 3. Policy Before Execution

No command, plugin, agent action, or external integration should execute before a policy decision is produced.

### 4. Isolation Is Concrete

Production sandboxing must not rely only on structured validation.

For real command execution, production requires:

- separate process or container boundary
- restricted filesystem
- restricted network
- resource limits
- environment filtering
- auditable command lifecycle

### 5. Human-Controlled Escalation

Dangerous actions require explicit user approval.

Examples:

- source modification
- Git commit/push/PR
- network access
- Docker daemon access
- dependency installation
- deletion
- writing outside scratch/workspace paths

### 6. Audit Is Immutable

Security decisions must be append-only and tamper-evident.

## Layered Architecture

```text
User / Agent / Plugin / Terminal
  -> Action Request
     -> Permission Engine
        -> Sandbox Guard
           -> Approval Gate
              -> Isolation Runner
                 -> Filesystem Policy
                 -> Network Policy
                 -> Resource Limits
                 -> Execution Result
                    -> Audit Logger
                    -> Threat Detector
                    -> Kill Switch
```

## Core Services

### Security Kernel

Responsibilities:

- own permission engine
- own sandbox guard
- own audit logger
- own kill switch
- own threat detector
- expose one security decision API

Canonical candidate:

```text
core/security
```

Rationale:

- current `core/security` is the strongest canonical candidate
- active graph runtime already validates through `core/security`
- duplication audit recommends merging duplicate sandbox/security services into one contract

### Action Classifier

Responsibilities:

- classify requested action
- detect risk category
- map action to permissions
- detect destructive intent
- detect network intent
- detect filesystem scope

Action classes:

```text
ReadOnly
RepositoryRead
RepositoryWrite
SourceModify
MemoryRead
MemoryWrite
GitRead
GitWrite
Network
Docker
Plugin
TerminalCommand
SecretAccess
Destructive
Unknown
```

Unknown actions are denied or require explicit approval depending on mode.

### Permission Engine

Responsibilities:

- evaluate actor/action/resource
- enforce explicit deny precedence
- reject wildcards
- report missing permissions
- produce structured decision

Existing `PermissionEngine` already supports:

- deny-by-default
- explicit allow/deny rules
- no wildcard actions/resources/permissions
- missing permission reporting

Production additions:

- load authoritative config from `config/permissions.yaml`
- support scoped grants with expiration
- support task-local grants
- support approval-derived temporary grants
- record decision trace

### Sandbox Guard

Responsibilities:

- enforce invariant security rules
- translate sandbox request into permission request
- validate filesystem mode
- validate network mode
- block source modification unless explicitly allowed by a higher workflow
- audit every sandbox decision
- consult kill switch before execution

Existing `SandboxGuard` already enforces:

- `filesystem == sandbox_only`
- network modes limited to disabled or explicit
- `source.modify` blocked
- `sandbox.execute` permission required
- `network.explicit` permission required for explicit network mode

Production additions:

- filesystem path allowlist validation
- network destination allowlist validation
- command risk class validation
- resource limit policy validation
- runner profile selection

### Approval Gate

Responsibilities:

- request human approval for elevated actions
- record approval scope
- expire approval
- bind approval to exact command/action
- show rollback and risk

Approval scopes:

```text
once
task
session
never for this action
```

Production default:

```text
approve once
```

### Isolation Runner

Responsibilities:

- execute approved real commands safely
- enforce process/container isolation
- stream output through terminal architecture
- return structured result
- preserve audit trail

Runner modes:

1. Validation-only runner
2. Local restricted process runner
3. Containerized runner
4. Worktree runner

Default production mode for real commands:

```text
containerized runner or restricted process runner
```

Validation-only mode remains valid for graph simulation and design tasks.

## Sandboxing

### Sandbox Profiles

#### Read-Only Profile

Purpose:

- repository search
- file inspection
- status checks
- diagnostics

Permissions:

- repository read
- no writes
- no network
- no Docker
- no secrets

Filesystem:

```text
workspace: read-only
scratch: writable
host: denied
```

Network:

```text
disabled
```

#### Workspace-Write Profile

Purpose:

- approved code edits
- generated docs
- test fixture updates

Permissions:

- repository write to allowed paths
- no host writes
- no raw source modification unless task is approved for editing
- no network by default

Filesystem:

```text
workspace: constrained write
scratch: writable
host: denied
```

#### Test Runner Profile

Purpose:

- compile checks
- tests
- static analysis

Permissions:

- repository read
- generated cache writes to approved paths
- no source writes unless explicitly approved
- no network by default

Filesystem:

```text
workspace: read-only preferred
approved cache dirs: writable
scratch: writable
```

#### Network-Explicit Profile

Purpose:

- dependency metadata checks
- provider API calls
- Git fetch/push
- documentation lookup

Permissions:

- `network.explicit`
- destination allowlist required
- operation-specific permission required

Filesystem:

```text
same as base profile
```

Network:

```text
allowlisted egress only
```

#### Docker Profile

Purpose:

- Docker build
- Docker inspect
- Compose config checks

Permissions:

- Docker access requires explicit approval
- network behavior must be shown separately
- daemon access must be treated as high risk

Filesystem:

```text
workspace read access
build context constrained
```

Risk:

Docker daemon access can effectively grant host-level power. It must be elevated.

#### Plugin Profile

Purpose:

- declarative plugin execution

Permissions:

- plugin must be registered
- plugin must be started
- plugin manifest permissions must match action
- plugin execution must pass sandbox guard

Blocked:

- dynamic import
- arbitrary path entrypoint
- `exec`
- `eval`
- subprocess
- host filesystem

## Filesystem Isolation

### Filesystem Zones

```text
Repository Zone
  project files under workspace root

Scratch Zone
  temporary task workspace

Generated Zone
  approved generated artifacts

Cache Zone
  test/build/tool caches

Vault Reference Zone
  secret references only, no raw secret files

Host Zone
  everything outside approved workspace/scratch
```

### Default Policy

```text
repository read: allowed for approved task context
repository write: requires approval
scratch write: allowed
generated write: allowed when task-approved
cache write: allowed for test/build profile
vault raw read: denied
host read: denied by default
host write: denied always
```

### Path Validation

Every path must be canonicalized before policy evaluation.

Required checks:

- resolve symlinks
- reject path traversal
- reject absolute host paths unless explicitly allowed
- ensure target remains under allowed root
- check hidden sensitive paths
- check generated/cache classification

Blocked paths:

```text
.git internals except through Git service
.env
private keys
credential files
SSH keys
system paths
parent directories outside workspace
```

### Workspace Writes

Workspace writes require:

- task-level approval
- ownership tracking
- diff generation
- rollback path
- no secret leakage
- audit record

ANUBIS-authored writes must be distinguishable from pre-existing user changes.

### Scratch Filesystem

Scratch path:

```text
.anubis/scratch/<task_id>/
```

Rules:

- writable by task
- cleaned by retention policy
- never trusted as source
- no execution from scratch unless explicitly approved
- logs and generated intermediate artifacts allowed

### Worktree Isolation

For code-changing tasks, prefer Git worktrees:

```text
.anubis/worktrees/<task-slug>/
```

Benefits:

- isolates concurrent changes
- avoids branch switching surprises
- protects user dirty state
- limits write scope

## Network Isolation

### Default Policy

```text
network: disabled
```

This matches the current Docker default `network_mode: none`.

### Explicit Network Mode

Network requires:

- explicit user approval
- `network.explicit` permission
- operation-specific permission
- destination classification
- audit record

Allowed network classes:

```text
GitRemote
PackageRegistry
Documentation
ModelProvider
VectorDatabase
Webhook
Other
```

Default allowlist:

```text
empty
```

### Network Request Model

```text
NetworkRequest
  actor
  operation
  destination_host
  destination_port
  protocol
  purpose
  required_permissions
  data_classification
```

Data classifications:

```text
public
repository_metadata
diff_summary
prompt_context
secret_reference
secret_value
unknown
```

`secret_value` is denied.

### Egress Controls

Production should enforce egress at multiple layers:

1. Application permission check
2. Runner network namespace/container network policy
3. Destination allowlist
4. DNS restrictions where feasible
5. Audit logging

### Network Actions

| Action | Default | Required Permission |
| --- | --- | --- |
| Git fetch | approval | `git.fetch`, `network.explicit` |
| Git push | approval | `git.push`, `network.explicit` |
| Open PR | approval | `git.pr.create`, `network.explicit` |
| Package install | approval/high risk | `dependency.install`, `network.explicit` |
| Web search | approval | `web.read`, `network.explicit` |
| Model API call | approval/high risk | `model.invoke`, `network.explicit` |
| Raw socket | denied | none |

## Permission System

### Permission Vocabulary

Recommended permission families:

```text
repository.read
repository.write
source.modify
memory.read
memory.write
memory.secret.reference
memory.secret.raw
rag.retrieve
rag.index
sandbox.execute
terminal.command
terminal.command.destructive
git.status
git.diff
git.branch.create
git.commit
git.push
git.pr.create
network.explicit
network.raw
docker.inspect
docker.build
docker.run
plugin.register
plugin.execute
audit.read
security.status.read
kill_switch.trigger
```

Forbidden by default:

```text
source.modify
memory.secret.raw
network.raw
filesystem.host
os.exec
subprocess.spawn
plugin.dynamic_import
```

### Actors

Actor classes:

```text
user
planner
executor
reviewer
terminal
git_service
memory_service
rag_service
plugin:<id>
system
```

Each actor receives minimal baseline permissions.

### Permission Decision Flow

```text
ActionRequest
  -> normalize actor/action/resource
  -> classify risk
  -> check kill switch
  -> check explicit deny
  -> check grant
  -> check sandbox invariants
  -> check approval if elevated
  -> allow or deny
  -> audit decision
```

### Temporary Grants

Human approval may create temporary grants.

Fields:

```text
TemporaryGrant
  actor
  permissions
  resource_scope
  task_id
  expires_at
  approval_id
```

Rules:

- never grant wildcard permissions
- never grant forbidden permissions silently
- expire at task/session boundary
- audit creation and use

### Permission Sources

Priority order:

1. Hardcoded critical denies
2. Kill switch state
3. Runtime policy config
4. Actor baseline grants
5. Task-scoped grants
6. Human approval grants
7. Plugin manifest grants

Explicit deny always wins.

## Secrets Security

Secrets must be references, not values.

Rules:

- raw secret values denied in memory
- raw secret values redacted in logs
- raw secret values blocked in telemetry export
- secret references may be attached to tasks
- secret access attempts are audited
- network requests carrying secrets require elevated approval and destination allowlist

Blocked storage:

- repository files
- memory records
- audit metadata
- terminal history
- plugin manifests

## Plugin Security

Plugins are high-risk because they expand capability surface.

Production plugin rules:

- manifest-only registration
- static symbolic entrypoints
- no dynamic import
- no arbitrary file path execution
- no subprocess by default
- plugin-specific actor identity
- permissions from manifest
- sandbox decision per invocation
- audit every lifecycle and execution event

Plugin lifecycle:

```text
registered -> validated -> started -> executable -> stopped
```

Execution requires:

- registered plugin
- started state
- manifest permission
- actor permission
- sandbox approval
- no kill switch block

## Terminal Security

Terminal execution must use the same security layer.

Command flow:

```text
terminal input
  -> action classifier
  -> permission engine
  -> sandbox guard
  -> approval gate
  -> isolated runner
  -> execution log
```

High-risk commands:

- deletes
- chmod/chown
- package installation
- Docker
- Git push/commit
- network tools
- writes outside workspace

Terminal must show:

- sandbox mode
- network mode
- cwd
- approval state
- command origin
- risk class

## Git Security

Git operations are separated by risk.

Low risk:

- status
- diff
- log
- branch list

Medium risk:

- branch create
- stage
- commit

High risk:

- push
- PR creation
- force push
- branch delete
- reset

Default policy:

- read operations allowed
- local mutating operations require approval
- remote operations require approval and network permission
- force push disabled by default
- merge PR out of scope

## Memory and RAG Security

Memory access requires isolation policy.

Rules:

- task-scoped memory visible to same task/session
- repository memory visible to matching workspace
- vault memory exposes references only
- conversation memory must redact secrets before indexing
- raw secret memory is denied
- cross-workspace retrieval requires explicit approval

RAG indexing must:

- deduplicate chunks
- avoid indexing secret files
- avoid indexing ignored/private files by default
- record collection and source metadata
- audit indexing of sensitive classes

## Audit and Kill Switch

### Required Audit Events

- permission allowed
- permission denied
- sandbox allowed
- sandbox denied
- approval requested
- approval granted
- approval denied
- command started
- command denied
- command completed
- plugin executed
- plugin denied
- network requested
- network denied
- filesystem write requested
- secret access attempted
- kill switch triggered

### Audit Record Requirements

```text
AuditRecord
  timestamp
  sequence
  actor
  action
  resource
  allowed
  reason
  trace_id
  task_id
  metadata
  previous_hash
  record_hash
```

### Kill Switch Triggers

Immediate review:

- sandbox escape attempt
- non-sandbox filesystem request
- raw network request
- source modification attempt outside approved flow
- repeated sandbox denials
- direct OS execution attempt
- plugin dynamic import attempt
- audit write failure

When active:

- allow `security.status.read`
- allow `audit.read`
- deny all other mutating actions

## Production Deployment Layers

### Container Layer

Required controls:

- non-root UID/GID
- read-only root filesystem
- no-new-privileges
- drop all capabilities
- no privileged mode
- no default network
- constrained tmpfs
- CPU/memory/PID/file descriptor limits

### Runner Layer

Required controls:

- per-task runner identity
- workspace/worktree mount policy
- scratch mount
- no host mount by default
- egress disabled by default
- timeout and resource limits
- output redaction

### Application Layer

Required controls:

- permission engine
- sandbox guard
- approval gate
- audit logging
- kill switch
- threat detector

### Human Workflow Layer

Required controls:

- explicit approval for elevated actions
- visible rollback
- diff review before commit
- PR review before merge
- no autonomous production release

## Configuration Authority

Production security requires config to be authoritative.

Canonical config files:

- `config/permissions.yaml`
- `config/sandbox.yaml`
- `config/production_hardening.yaml`
- `config/secrets_policy.yaml`
- `config/audit_policy.yaml`

Required behavior:

- load config at startup
- validate config schema
- reject wildcard permissions
- reject unknown forbidden permission grants
- expose effective policy in security status
- test effective runtime against config

## Migration Plan

### Phase 1: Clarify Semantics

Deliverables:

- document current sandbox as authorization/validation
- define production isolation runner contract
- make `core/security` canonical
- map `src/anubis/sandbox.py` concepts into canonical contract

Risk:

```text
Low
```

### Phase 2: Authoritative Policy Loading

Deliverables:

- load permission and sandbox config into runtime
- validate config at startup
- expose effective policy
- add tests comparing effective policy to config

Risk:

```text
Medium
```

### Phase 3: Durable Audit

Deliverables:

- append-only audit JSONL or SQLite store
- hash-chain verification
- redaction before persistence
- audit replay and integrity check

Risk:

```text
Medium
```

### Phase 4: Isolated Runner

Deliverables:

- local restricted runner or container runner
- per-command sandbox profile
- resource limits
- filesystem mount policy
- network disabled by default
- output streaming through terminal architecture

Risk:

```text
High
```

Primary concern:

- this is the point where ANUBIS moves from simulated/validated execution toward real process execution

### Phase 5: Network Allowlist

Deliverables:

- destination allowlist
- network request classification
- explicit approval flow
- network audit events
- egress tests

Risk:

```text
Medium-High
```

### Phase 6: Plugin Hardening

Deliverables:

- plugin permission contract
- manifest validation
- plugin execution isolation
- lifecycle audit
- dynamic import enforcement tests

Risk:

```text
Medium
```

## Validation Plan

Required tests:

- permission deny-by-default
- explicit deny precedence
- wildcard grant rejection
- sandbox denies host filesystem
- sandbox denies raw network
- sandbox denies source modification outside approved flow
- kill switch blocks mutating actions
- audit hash-chain integrity
- secret redaction
- path traversal rejection
- symlink escape rejection
- network allowlist enforcement
- plugin dynamic import rejection
- terminal destructive command approval
- Docker access approval

Required tools/commands:

```bash
PYTHONPATH=src:. python3 scripts/run_tests.py
PYTHONPATH=src:. python3 tools/sandbox_tester.py
python3 -m compileall core src tests
docker compose config
```

Production escape tests:

- attempt write outside workspace
- attempt symlink traversal
- attempt read `.env`
- attempt raw network connection
- attempt subprocess spawn from plugin
- attempt dynamic import from plugin
- attempt Docker access without approval

## Acceptance Criteria

Production security is ready when:

- current sandbox semantics are documented as validation unless isolated runner is active
- all real execution passes through the security kernel
- permission config is authoritative and tested
- no wildcard permissions are accepted
- filesystem writes are constrained to approved zones
- host filesystem access is denied by default
- network is disabled by default
- network access requires explicit permission and approval
- plugin execution is manifest-scoped and sandbox-approved
- terminal commands use the same permission/sandbox flow
- audit records are durable and tamper-evident
- kill switch blocks all mutating actions when active
- escape tests pass in CI

## Final Architecture Contract

```text
Security Kernel
  owns permission engine, sandbox guard, audit logger, kill switch, threat detector

Permission System
  deny-by-default, explicit deny precedence, no wildcards, task-scoped temporary grants

Sandbox Layer
  validates invariants, filesystem mode, network mode, resource profile, approval state

Isolation Runner
  provides concrete process/container isolation for real command execution

Filesystem Isolation
  repository/worktree/scratch/cache zones, canonical path validation, host denial

Network Isolation
  disabled by default, explicit network permission, destination allowlist, audited egress

Audit and Response
  append-only hash-chain records, threat detection, one-way kill switch for critical events
```

This architecture preserves ANUBIS's local-first security posture while defining the additional production isolation needed before real command, plugin, or network execution can be trusted.
