# ANUBIS Secure Sandbox Execution Layer

Date: 2026-06-05

Role: Security Engineer

## Goal

Design a secure sandbox execution layer for ANUBIS.

Requirements:

- isolate code execution from host system
- prevent filesystem access outside sandbox
- prevent network abuse
- limit CPU and memory usage
- ensure deterministic execution environment

This is a design document. It does not modify runtime behavior.

## Executive Summary

ANUBIS currently has a strong authorization sandbox, but real process execution must be isolated by a concrete container boundary before production use.

The secure sandbox layer should operate as:

```text
core approval
  -> sandbox permission check
     -> Docker-based isolated execution container
        -> streamed logs
           -> structured result
              -> audit + memory evidence
```

The sandbox must never expose:

- host filesystem
- Docker socket
- privileged container mode
- raw network by default
- repository write access by default
- secrets as raw environment variables

## Current State

Existing controls:

- `core/security/SandboxGuard`
- `core/security/PermissionEngine`
- `core/security/AuditLogger`
- `core/security/KillSwitch`
- `config/sandbox.yaml`
- `docker-stack.yml` service isolation for `anubis-sandbox`

Current limitation:

The active graph path validates sandbox requests but does not execute arbitrary OS commands. Production command execution needs a separate Docker-based runner.

## Security Threat Model

### Protected Assets

- host filesystem
- repository source
- user uncommitted changes
- secrets and credentials
- memory/Qdrant data
- Git credentials
- Docker daemon
- audit logs
- service network

### Threats

| Threat | Example | Required Control |
| --- | --- | --- |
| Host filesystem escape | read `/home`, `/etc`, SSH keys | no host mounts, path allowlist |
| Sandbox breakout | privileged container, added capabilities | no privileged mode, drop capabilities |
| Docker socket abuse | mount `/var/run/docker.sock` | never mount Docker socket |
| Network abuse | exfiltrate data, scan services | network disabled by default |
| Resource exhaustion | fork bomb, memory spike | CPU/memory/PID limits |
| Secret leakage | env dump, logs expose tokens | no raw secrets, redaction |
| Source tampering | overwrite repo files | read-only workspace by default |
| Non-determinism | mutable image, live network deps | pinned images, no network, fixed env |
| Audit bypass | run command outside logging path | all execution through sandbox API |

### Trust Boundaries

```text
User/UI
  untrusted input

anubis-core
  trusted control plane, no direct execution

anubis-sandbox
  trusted policy executor, isolated from host

execution container
  untrusted workload

host
  must be protected from workload
```

## Sandbox Architecture

```text
anubis-core
  -> POST /v1/sandbox/commands
     -> anubis-sandbox API
        -> permission model
        -> sandbox profile resolver
        -> Docker execution controller
           -> isolated execution container
              -> stdout/stderr stream
              -> exit code
        -> result normalizer
        -> audit/event emission
```

## Components

### Sandbox API

Responsibilities:

- accept command requests from `anubis-core`
- reject direct UI calls for mutating execution
- validate idempotency key
- validate actor/task/trace metadata
- expose execution status and streams

Suggested endpoints:

```text
POST /v1/sandbox/validate
POST /v1/sandbox/commands
GET  /v1/sandbox/commands/{command_id}
GET  /v1/sandbox/commands/{command_id}/stream
POST /v1/sandbox/commands/{command_id}/cancel
GET  /v1/sandbox/profiles
```

### Permission Model

Every command request must include:

```text
actor
task_id
trace_id
operation
profile
argv
cwd
filesystem_mode
network_mode
resource_limits
idempotency_key
```

Decision flow:

```text
validate request schema
  -> classify command risk
  -> check kill switch
  -> check permission engine
  -> check sandbox invariants
  -> require approval if elevated
  -> launch or deny
```

Default permissions:

```text
sandbox.execute: required for all execution
network.explicit: required for any network
filesystem.write: required for writable workspace
source.modify: denied by default
filesystem.host: denied always
network.raw: denied always
docker.socket: denied always
```

## Container Isolation Strategy

### Runner Model

`anubis-sandbox` should not execute user commands in its own service container. It should launch short-lived execution containers with a locked-down runtime profile.

```text
anubis-sandbox service container
  trusted controller

sandbox-runner container
  untrusted task workload
  one command or bounded command group
```

Important:

The controller must not mount the host Docker socket unless an alternative hardened runner boundary is unavailable and explicitly approved. Preferred production model is a dedicated worker runtime API, rootless Docker/Podman, or container runtime socket isolated to sandbox workers only.

### Docker Runtime Controls

Required options for execution containers:

```text
--read-only
--network none
--cap-drop ALL
--security-opt no-new-privileges:true
--pids-limit 128
--memory 256m
--memory-swap 256m
--cpus 1.0
--user 10001:10001
--tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m
--workdir /sandbox
```

Do not allow:

```text
--privileged
--cap-add
--pid host
--ipc host
--network host
--mount type=bind,source=/
--device
Docker socket mount
```

### Filesystem Layout

Inside runner:

```text
/sandbox
  working directory

/tmp
  tmpfs only

/workspace
  optional read-only task workspace mount

/artifacts
  optional writable output volume for approved artifacts only
```

Default:

```text
/workspace: read-only or absent
/artifacts: absent
/tmp: writable tmpfs
host paths: denied
```

### Path Rules

All paths must be:

- canonicalized before use
- checked against allowed roots
- rejected if symlink escapes allowed root
- rejected if absolute host path is requested
- rejected if path traversal is present

Blocked paths:

```text
/
/home
/etc
/var/run
/var/run/docker.sock
/root
/proc host mounts
/sys host mounts
.git internals unless Git service owns the operation
.env and secret files
```

## Network Isolation

Default:

```text
network disabled
```

Network-enabled execution requires:

- explicit user approval
- `network.explicit` permission
- destination allowlist
- data classification
- audit record
- separate network-enabled profile

Allowed network profiles:

```text
none
  default; no egress

internal-only
  limited access to approved ANUBIS internal services

allowlisted-egress
  explicit destination list, time-bounded
```

Forbidden:

```text
host network
raw sockets
service discovery scans
unrestricted package installs
secret-bearing outbound requests
```

## Resource Limits

Default profile:

```text
timeout_seconds: 30
memory_mb: 256
cpu_quota: 1.0
pids_limit: 128
stdout_limit_mb: 16
stderr_limit_mb: 16
artifact_limit_mb: 64
```

Behavior:

- timeout kills the runner container
- memory overage fails command
- output beyond limit is truncated and summarized
- PID limit prevents fork bombs
- CPU limit prevents scheduler abuse

## Deterministic Execution Environment

Determinism controls:

- pinned runner images by digest
- no network by default
- fixed environment variables
- fixed working directory
- read-only root filesystem
- explicit mounted inputs
- no host clock dependency beyond timestamps
- no hidden host toolchain access
- no mutable package installation during execution

Environment:

```text
ANUBIS_ENV=production
ANUBIS_SANDBOX=enforced
HOME=/nonexistent
PATH=/usr/local/bin:/usr/bin:/bin
LANG=C.UTF-8
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
```

Remove:

- host secrets
- cloud credentials
- SSH agent sockets
- Git credentials
- Docker host variables

## Sandbox Profiles

### validate-only

Purpose:

- current graph parity
- no process execution

Filesystem:

```text
none
```

Network:

```text
disabled
```

### read-only-workspace

Purpose:

- inspect files
- run static read-only checks

Filesystem:

```text
/workspace read-only
/tmp writable tmpfs
```

Network:

```text
disabled
```

### test-runner

Purpose:

- run compile/tests in a controlled environment

Filesystem:

```text
/workspace read-only by default
/tmp writable tmpfs
optional cache tmpfs
```

Network:

```text
disabled
```

### artifact-writer

Purpose:

- produce approved reports or generated artifacts

Filesystem:

```text
/workspace read-only
/artifacts writable isolated volume
```

Network:

```text
disabled
```

### network-explicit

Purpose:

- approved integration checks

Filesystem:

```text
same as read-only-workspace unless approved otherwise
```

Network:

```text
allowlisted only
```

## Execution Lifecycle

### 1. Request

Core sends:

```json
{
  "trace_id": "trace_...",
  "task_id": "task_...",
  "actor": "anubis-core",
  "profile": "test-runner",
  "argv": ["python3", "-m", "compileall", "core", "src"],
  "cwd": "/workspace",
  "network": "disabled",
  "filesystem": "read-only-workspace",
  "limits": {
    "timeout_seconds": 30,
    "memory_mb": 256,
    "cpu_quota": 1.0,
    "pids_limit": 128
  },
  "idempotency_key": "idem_..."
}
```

### 2. Authorization

Sandbox checks:

- schema validity
- actor permission
- command risk
- filesystem mode
- network mode
- resource limits
- kill switch
- approval state

### 3. Prepare

Sandbox creates:

- command id
- scratch directory or tmpfs config
- execution profile
- redaction policy
- stream buffer

### 4. Launch

Sandbox starts isolated container with:

- pinned image
- readonly root
- no network
- no capabilities
- no new privileges
- memory/CPU/PID limits
- approved mounts only

### 5. Stream

Sandbox streams:

- stdout
- stderr
- status events
- resource events

Stream events are sequenced:

```text
command.queued
command.authorized
command.started
command.output
command.completed
command.failed
command.timed_out
```

### 6. Collect

Sandbox records:

- exit code
- duration
- stdout/stderr references
- truncated output markers
- resource usage
- sandbox profile
- audit decision

### 7. Cleanup

Sandbox removes:

- runner container
- scratch files
- temporary volumes
- network attachments

Retains:

- redacted logs
- command metadata
- approved artifacts
- audit records

### 8. Report

Response:

```json
{
  "command_id": "cmd_...",
  "status": "completed",
  "exit_code": 0,
  "duration_ms": 1842,
  "profile": "test-runner",
  "network": "disabled",
  "filesystem": "read-only-workspace",
  "stdout_ref": "log_...",
  "stderr_ref": "log_...",
  "resource_usage": {
    "memory_peak_mb": 72,
    "cpu_ms": 931
  }
}
```

## Audit Requirements

Audit every:

- command request
- permission decision
- sandbox decision
- approval decision
- container launch
- command completion/failure
- timeout
- cancellation
- denied filesystem request
- denied network request

Audit record fields:

```text
timestamp
trace_id
task_id
command_id
actor
action
resource
allowed
reason
profile
filesystem
network
limits
image_digest
metadata
```

## Failure Handling

### Command Timeout

Action:

- stop runner container
- mark `timed_out`
- preserve logs
- emit audit event

### Memory Limit Exceeded

Action:

- mark `resource_limit_exceeded`
- preserve logs
- block automatic retry unless user approves larger profile

### Network Denied

Action:

- deny before launch where possible
- if runtime detection occurs, terminate command
- create high-severity security event

### Filesystem Escape Attempt

Action:

- deny before launch
- trigger SOC alert
- activate kill switch if policy classifies as critical

### Controller Failure

Action:

- runner commands have timeout labels
- orphan cleanup reconciler removes stale containers
- command state rebuilt from event/audit log

## Docker-Based Isolation Strategy

### Swarm Service Isolation

`anubis-sandbox` service:

- no public ingress
- internal execution network only
- read-only root filesystem
- non-root user
- dropped capabilities
- no host mounts
- no Docker socket

### Execution Container Isolation

Runner containers:

- short-lived
- one command per container
- no host filesystem
- no host network
- no privileged mode
- resource-limited
- deterministic image digest

### Recommended Runner Host Model

Preferred:

```text
dedicated sandbox worker nodes
rootless container runtime
no production secrets on nodes
no co-location with memory/Qdrant
node label: anubis.sandbox=true
```

Avoid:

```text
sandbox workers on manager nodes
sandbox workers with Docker socket exposed to app container
sandbox workers sharing Qdrant volumes
```

## Validation Tests

Required tests:

- cannot read host `/etc/passwd`
- cannot access `/var/run/docker.sock`
- cannot write outside `/tmp` or approved artifact mount
- symlink escape fails
- path traversal fails
- network request fails in default profile
- CPU limit enforced
- memory limit enforced
- PID limit enforced
- timeout kills container
- logs are redacted
- command result is audited
- kill switch blocks execution

Smoke commands:

```bash
python3 -m compileall core src
python3 scripts/run_tests.py
```

Escape simulation commands:

```bash
cat /etc/passwd
ls /var/run/docker.sock
python3 -c "open('/tmp/ok','w').write('ok')"
python3 -c "open('/workspace/should_fail','w').write('x')"
python3 -c "import socket; socket.create_connection(('example.com', 80), timeout=2)"
```

Expected:

- only approved `/tmp` write succeeds
- host and workspace writes fail
- network fails unless explicit profile is approved

## Acceptance Criteria

Sandbox execution is production-ready when:

- all real commands run in separate isolated containers
- no host filesystem is mounted into execution containers
- Docker socket is never exposed to untrusted workload
- default network is disabled
- network-enabled execution requires explicit permission and allowlist
- CPU, memory, PID, output, and timeout limits are enforced
- workspace is read-only unless a specific artifact profile is approved
- environment is deterministic and secret-free
- every command emits audit records and stream events
- cleanup removes runner containers and temporary files
- escape tests pass in CI

## Final Architecture Contract

```text
anubis-core
  approves and requests execution

anubis-sandbox
  authorizes, profiles, launches, streams, audits, and cleans up

sandbox-runner container
  executes exactly one approved workload under Docker isolation

filesystem
  read-only root, tmpfs scratch, optional read-only workspace, no host paths

network
  disabled by default, allowlisted only by explicit profile

resources
  CPU, memory, PID, timeout, output, and artifact limits

determinism
  pinned image, fixed env, no network, explicit inputs, no mutable host dependency
```

This design turns the current authorization sandbox into a production execution layer with concrete Docker isolation while preserving ANUBIS's deny-by-default security posture.
