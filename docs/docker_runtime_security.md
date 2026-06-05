# Docker Runtime Security Notes

ANUBIS is packaged as a local-first Python runtime with sandbox enforcement in
the application layer and container hardening in the runtime layer.

The complete production hardening baseline is documented in
`docs/production_hardening.md`.

## Default Runtime

Use the default service for production-like local runs:

```bash
docker compose up --build anubis
```

Default constraints:

- runs as UID/GID `10001:10001`, never root;
- Linux capabilities are dropped with `cap_drop: [ALL]`;
- `no-new-privileges` is enabled;
- container filesystem is read-only;
- only `/tmp` is writable, mounted as `tmpfs` with `noexec,nosuid,nodev`;
- network is disabled with `network_mode: "none"`;
- CPU, memory, PID, process, and file descriptor limits are set;
- restart policy is disabled to avoid hiding repeated failures.

## Explicit Network Opt-In

Network access is disabled by default. Use the separate profile only when a
reviewed integration requires egress:

```bash
docker compose --profile network-enabled up --build anubis-network-enabled
```

Application-level sandbox permissions must still explicitly allow any networked
action. The profile only provides container networking; it does not grant ANUBIS
plugin or task permissions.

## Deterministic Build Notes

The Dockerfile uses a versioned Python slim image pinned by digest:

```text
python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419
```

For release builds, update the digest intentionally in CI after image review:

```bash
docker build \
  --build-arg PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:<reviewed-digest> \
  -t anubis:<version> .
```

The runtime currently uses the Python standard library only, so the production
image does not install third-party packages.

## Sandbox Boundary

Container hardening does not replace ANUBIS sandbox enforcement. Plugins and
tasks must still pass through:

- permission engine;
- sandbox guard;
- audit logging;
- kill switch checks.

No plugin loader path imports runtime code dynamically. Plugin manifests are
declarative, and plugin execution must be mediated by the sandbox boundary.
