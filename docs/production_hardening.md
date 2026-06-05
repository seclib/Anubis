# Production Hardening

This document defines the minimum production hardening baseline for ANUBIS.
The baseline assumes ANUBIS remains local-first, sandbox-enforced, and
human-approved for releases.

## Threats Covered

ANUBIS must be safe against:

- arbitrary code execution;
- plugin abuse;
- sandbox escape attempts;
- unauthorized network access;
- unauthorized source modification;
- silent security failures.

## Container Isolation Rules

Production containers must use the hardened Compose profile in
`docker-compose.yml` and the policy in `config/production_hardening.yaml`.

Required runtime controls:

- run as UID/GID `10001:10001`, never root;
- drop all Linux capabilities;
- set `no-new-privileges`;
- disable privileged mode;
- use a read-only root filesystem;
- mount only `/tmp` as `tmpfs` with `noexec,nosuid,nodev`;
- disable networking by default with `network_mode: none`;
- set CPU, memory, swap, PID, process, and file descriptor limits;
- avoid restart loops that hide repeated failures.

Network access is opt-in only through the `network-enabled` Compose profile.
Enabling container networking does not grant ANUBIS runtime permissions. A task
or plugin still needs explicit `network.explicit` permission.

## Secrets Management Strategy

Secrets must never be stored inline in repository files, memory records, logs,
plugin manifests, or task payloads.

Production rules:

- store secrets in an external secret manager or Docker secrets;
- pass only references into ANUBIS, not raw values;
- deny `raw_secret` memory content;
- require external references for credentials;
- redact sensitive fields in logs and audit output;
- audit secret access attempts;
- fail CI if inline secret patterns are detected.

See `config/secrets_policy.yaml` for the machine-readable policy.

## Permission Boundaries

ANUBIS permissions are deny-by-default.

Required boundaries:

- no wildcard permissions;
- explicit deny rules override allow rules;
- every action must pass through permission validation;
- plugins must be registered, started, and sandbox-approved before execution;
- generated code execution is denied;
- runtime code injection is denied;
- direct OS access is denied;
- source modification is denied.

Forbidden permission classes:

- `source.modify`;
- `os.exec`;
- `subprocess.spawn`;
- `filesystem.host`;
- `network.raw`;
- `plugin.dynamic_import`.

## Execution Limits

All task and plugin execution must be mediated by the sandbox guard.

Default limits:

- timeout: 30 seconds;
- memory: 256 MB metadata limit for sandboxed tasks;
- retries: bounded by runtime policy;
- filesystem: sandbox-only;
- network: denied;
- rollback: required on final failure where a rollback handler exists.

Any request for non-sandbox filesystem access, source modification, or raw
network access is a critical sandbox escape attempt.

## Audit Logging Requirements

Security-relevant actions must be logged as structured append-only audit
records with hash-chain integrity.

Required audit events include:

- permission allowed or denied;
- sandbox allowed or denied;
- plugin registered, started, stopped, executed, denied, or failed;
- kill switch triggered;
- threat finding detected;
- memory append and retrieval;
- secret storage denied.

Audit records must include:

- timestamp;
- sequence;
- actor;
- action;
- resource;
- decision;
- reason;
- trace identifier;
- metadata.

See `config/audit_policy.yaml` for detailed event and retention requirements.

## Plugin Abuse Controls

Plugins must not load code dynamically at runtime.

Required controls:

- manifest loader reads declarative JSON only;
- plugin entrypoints are symbolic identifiers, not paths;
- no `exec`, `eval`, `importlib`, `__import__`, `subprocess`, or `os.system`;
- plugin input and output must be structured dictionaries;
- plugin execution must be audited;
- plugin failures must be structured and non-silent;
- plugin permissions come from the manifest and are checked by sandbox guard.

## Sandbox Escape Response

The following findings must trigger kill switch review:

- non-sandbox filesystem request;
- source modification attempt;
- repeated sandbox denials;
- direct OS execution attempt;
- plugin dynamic import attempt.

When the kill switch is active, only read-only security status and audit reads
are allowed.

## Release Safety

Production changes are never automatic.

Required controls:

- no automatic production deployment;
- no self-triggered production changes;
- no infrastructure mutation from CI;
- release workflow must use manual `production-release` environment approval;
- all tests, security scans, sandbox tests, and lint checks must pass before
  release approval.
