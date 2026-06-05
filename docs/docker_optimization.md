# ANUBIS Docker Optimization Audit

Date: 2026-06-05

## Goal

Reduce Docker image size by 70%.

Current image:

```text
anubis:local = 123.17 MB
```

70% reduction target:

```text
123.17 MB * 0.30 = 36.95 MB
```

Practical target:

```text
<= 37 MB
```

## Executive Summary

The current image is already clean at the application layer. ANUBIS has no runtime Python dependencies, no package installation step, and small source layers.

The size problem is almost entirely the base image:

- Debian base layer: `74.8 MB`
- Python build/runtime layer: `36.7 MB`
- CA/timezone/netbase layer: `9.25 MB`
- ANUBIS app layers: about `1.2 MB`

Therefore, a 70% reduction cannot come from ordinary Dockerfile cleanup. It requires changing the runtime packaging strategy.

## Current Docker Architecture

### Dockerfile

Current base:

```dockerfile
ARG PYTHON_IMAGE=python:3.13.5-slim-bookworm@sha256:...
FROM ${PYTHON_IMAGE}
```

Current runtime properties:

- Python `3.13.5` slim Bookworm image pinned by digest.
- No `pip install`.
- No OS package installation in ANUBIS Dockerfile.
- Non-root runtime user `10001:10001`.
- Read-only application files.
- Entrypoint: `python3 /app/bootstrap.py`.

Copied paths:

```text
bootstrap.py
pyproject.toml
requirements.txt
src/
core/
agents/
config/
```

Not copied due to `.dockerignore`:

```text
tests/
ci/
tools/
scripts/
docs/
audit/
__pycache__/
.ruff_cache/
```

### Docker Compose

Current hardening:

- `network_mode: none` by default
- non-root user
- read-only root filesystem
- dropped capabilities
- `no-new-privileges`
- PID, memory, CPU, process, and file descriptor limits
- tmpfs-only writable `/tmp`
- optional `network-enabled` profile

The Compose hardening is good and should be preserved.

## Current Image Metrics

Image inspect:

| Metric | Value |
| --- | ---: |
| Image | `anubis:local` |
| Size | `123,169,581 bytes` |
| Size | `123.17 MB` |
| Size | `117.46 MiB` |
| Layers | `12` |
| OS | `linux` |
| Architecture | `amd64` |

Layer history:

| Layer | Size |
| --- | ---: |
| Debian Bookworm base | `74.8 MB` |
| CA certificates, netbase, tzdata | `9.25 MB` |
| Python runtime/build layer | `36.7 MB` |
| user/group creation | `4.37 KB` |
| app root files | `806 B` |
| `src/` | `706 KB` |
| `core/` | `491 KB` |
| `agents/` | `17.8 KB` |
| `config/` | `6.11 KB` |
| chmod/read-only layer | `1.22 MB` |

Local source sizes:

| Path | Size |
| --- | ---: |
| `core` | `984 KB` |
| `src` | `1.4 MB` |
| `agents` | `64 KB` |
| `tests` | `456 KB` |
| repository total | `65 MB` |

## Layer Duplication Analysis

### App Layer Duplication

No significant app duplication exists in Docker layers.

The Dockerfile uses separate `COPY` instructions:

```dockerfile
COPY bootstrap.py pyproject.toml requirements.txt ./
COPY src ./src
COPY core ./core
COPY agents ./agents
COPY config ./config
```

This creates several small layers, but their combined size is around `1.2 MB`. Merging them would reduce layer count, not materially reduce image size.

Classification:

```text
Low impact
```

### Permission Layer Duplication

The chmod layer is `1.22 MB`.

Reason:

```dockerfile
RUN chmod -R a-w /app ...
```

This can create metadata changes in a new layer. Since files are already copied in previous layers, permission changes add a measurable layer.

Classification:

```text
Small but real impact
```

Possible optimization:

- Use `COPY --chmod` where practical.
- Set directory/file modes during copy.
- Reduce recursive chmod layer.

Estimated savings:

```text
~1 MB
```

### Base Layer Duplication

The image inherits:

- Debian base
- Python runtime
- CA/timezone utilities

These are not duplicate layers inside this image, but they dominate total size.

Classification:

```text
Primary optimization target
```

## Cache Usage Analysis

### Current Cache Strengths

Separate copy layers improve build cache behavior:

- changes to `src` do not invalidate `core`
- changes to `config` do not invalidate `src`
- no dependency install layer exists

Since there is no `pip install`, dependency cache optimization is not needed.

### Current Cache Weaknesses

The Dockerfile copies full source directories rather than installing a package or copying a curated runtime tree.

Potential issue:

- any file change inside `src` invalidates the entire `src` layer
- any file change inside `core` invalidates the entire `core` layer

But source layers are small, so this is not a major concern.

### `.dockerignore`

Current `.dockerignore` is good:

- excludes tests
- excludes docs
- excludes tools/scripts
- excludes caches
- excludes Docker files and Compose files

Potential concern:

The Dockerfile copies only explicit paths, so `.dockerignore` is not the main size control. It protects build context size and accidental copies.

## Build Strategy Assessment

Current build strategy:

```text
pinned Python slim base
copy source
chmod read-only
run as non-root
```

Strengths:

- secure
- deterministic
- simple
- no runtime dependencies
- no network required at runtime
- digest-pinned base

Weaknesses:

- Debian slim Python base cannot reach 70% size reduction.
- Python interpreter and Debian userspace dominate.
- Includes pip and Python tooling from base image even though runtime does not install packages.
- Chmod layer adds about `1.22 MB`.

## Optimization Options

## Option 1: Small Dockerfile Cleanup

Expected reduction:

```text
1-3%
```

Projected size:

```text
119-122 MB
```

Actions:

1. Replace recursive chmod layer with `COPY --chmod` where possible.
2. Combine app `COPY` instructions if layer count matters.
3. Continue excluding tests/docs/tools/audits.
4. Keep current Python slim base.

Pros:

- low risk
- preserves current security posture
- minimal changes

Cons:

- nowhere near 70% reduction

Recommendation:

Good hygiene, insufficient for stated goal.

## Option 2: Alpine Python Runtime

Expected reduction:

```text
35-55%
```

Projected size:

```text
55-80 MB
```

Strategy:

```dockerfile
FROM python:3.13-alpine
```

Pros:

- significant size reduction
- still easy to run Python source
- no app packaging changes

Cons:

- not enough for 70% target in most cases
- musl libc differences
- less parity with Debian
- some Python wheels break if dependencies are added later
- security and debugging behavior differs

Recommendation:

Useful medium-risk option if the 70% target can be relaxed, but not the best strategic target.

## Option 3: Distroless Python Runtime

Expected reduction:

```text
45-65%
```

Projected size:

```text
43-68 MB
```

Strategy:

- build or use a distroless Python runtime
- copy only Python interpreter, standard library subset, and ANUBIS source
- run as non-root

Pros:

- smaller than Debian slim
- reduced shell/package-manager attack surface
- aligns with hardened runtime goals

Cons:

- may still miss 70%
- harder debugging
- no shell
- requires careful Python stdlib coverage
- digest pinning and provenance must be managed

Recommendation:

Best security-aligned path if the team accepts operational complexity.

## Option 4: Standalone Python Executable

Expected reduction:

```text
60-75%
```

Projected size:

```text
30-50 MB
```

Strategy:

- package ANUBIS as a standalone executable using a Python freezing/build tool
- copy the executable into a minimal runtime image
- runtime base could be distroless, Wolfi, Alpine, or scratch-like if fully static

Possible tool classes:

- PyInstaller-style bundle
- Nuitka-style compiled binary
- PyOxidizer-style embedded Python
- PEX/shiv plus minimal Python runtime, though this still needs Python

Pros:

- only realistic path to the 70% target
- can remove most Debian/Python image overhead
- app is standard-library only, which helps

Cons:

- introduces a build toolchain
- may complicate stack traces and debugging
- needs reproducibility work
- may alter startup behavior
- requires careful license/provenance review
- may be overkill for a small local-first runtime

Recommendation:

Primary path for the stated 70% reduction goal.

## Option 5: Custom Minimal CPython Runtime

Expected reduction:

```text
60-75%
```

Projected size:

```text
30-50 MB
```

Strategy:

- multi-stage build
- copy only:
  - `python3`
  - required shared libraries
  - required Python standard library modules
  - ANUBIS source
- remove pip, ensurepip, tests, idle, distutils remnants, unused stdlib modules

Pros:

- keeps source execution model
- can reach the target with enough trimming
- no app-level freezing required

Cons:

- high maintenance
- fragile stdlib trimming
- Python imports can fail if a module is omitted
- harder security patching
- requires automated smoke tests inside image

Recommendation:

Possible but higher maintenance than a known minimal/distroless Python runtime.

## Recommended Target Strategy

Use a two-track plan:

```text
Track A: Low-risk hygiene
Track B: 70% reduction runtime redesign
```

### Track A: Low-Risk Hygiene

Expected result:

```text
~121 MB
```

Steps:

1. Remove tracked bytecode and caches from repository.
2. Use `COPY --chmod` to avoid the `1.22 MB` chmod layer.
3. Keep `.dockerignore` strict.
4. Keep current Compose hardening.

This improves cleanliness but does not materially reduce size.

### Track B: 70% Reduction Runtime Redesign

Target:

```text
<= 37 MB
```

Recommended approach:

1. Add a build stage that creates a standalone ANUBIS runtime artifact.
2. Add a minimal runtime stage that contains only the artifact and required runtime files.
3. Preserve non-root UID/GID.
4. Preserve read-only root filesystem in Compose.
5. Preserve `network_mode: none`.
6. Add image smoke tests for:
   - `python/bootstrap` equivalent starts
   - graph run succeeds
   - no source write attempt required
   - no network needed

Preferred target image family:

- distroless/static-like runtime if standalone executable is used
- minimal Python runtime only if freezing is rejected

## Proposed Future Dockerfile Shape

Design sketch only:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS builder
WORKDIR /build
COPY bootstrap.py pyproject.toml requirements.txt ./
COPY src ./src
COPY core ./core
COPY agents ./agents
COPY config ./config

# Build standalone artifact here.
# Example class: PyInstaller/Nuitka/PyOxidizer.
# Output: /build/dist/anubis

FROM gcr.io/distroless/base-debian12:nonroot AS runtime
WORKDIR /app
COPY --from=builder --chown=nonroot:nonroot /build/dist/anubis /app/anubis
COPY --from=builder --chown=nonroot:nonroot /build/config /app/config
USER nonroot:nonroot
ENTRYPOINT ["/app/anubis"]
```

This is an architectural direction, not an immediate implementation.

## Layer Duplication Fixes

Near-term Dockerfile improvements:

| Issue | Current | Proposed | Savings |
| --- | --- | --- | ---: |
| chmod metadata layer | recursive chmod creates `1.22 MB` layer | use `COPY --chmod` or copy pre-normalized modes | ~`1 MB` |
| many small app copy layers | separate `COPY` for src/core/agents/config | optional combined runtime copy | tiny |
| bytecode/caches in source tree | excluded by `.dockerignore`, but tracked locally | remove from repo | build context hygiene |
| base image overhead | Python slim Bookworm | standalone/minimal runtime | 60-75% |

## Build Cache Strategy

Recommended cache strategy:

1. Keep source copy late in the Dockerfile.
2. If a builder tool is added, copy dependency/build config before source.
3. Use BuildKit cache mounts for build tooling:

```dockerfile
RUN --mount=type=cache,target=/root/.cache ...
```

4. Do not cache runtime-generated files in final image.
5. Keep final image single-purpose and immutable.

Because ANUBIS has no runtime dependencies, dependency-layer caching is not currently needed.

## Security Constraints to Preserve

Any optimized image must preserve:

- non-root runtime
- no writeable app source
- read-only root filesystem via Compose
- dropped Linux capabilities
- `no-new-privileges`
- default no-network profile
- tmpfs-only `/tmp`
- no auto-deployment behavior
- no generated-code execution

Size reduction must not remove these controls.

## Risk Assessment

| Strategy | Size Reduction | Risk | Notes |
| --- | ---: | --- | --- |
| Chmod/COPY cleanup | 1-3% | Low | Safe, insufficient. |
| Alpine Python | 35-55% | Medium | Simpler but likely misses 70%. |
| Distroless Python | 45-65% | Medium-High | Good hardening, may miss 70%. |
| Standalone executable | 60-75% | High | Best chance to hit target. |
| Custom CPython runtime | 60-75% | High | Fragile and maintenance-heavy. |

## Measurement Targets

| Metric | Current | Target |
| --- | ---: | ---: |
| Image size | `123.17 MB` | `<= 36.95 MB` |
| Layers | `12` | `<= 8` |
| App source layers | ~`1.2 MB` | `<= 1.5 MB` |
| Startup median | `~221 ms` | `<= 250 ms` |
| Peak RSS | `~29 MB` | `<= 40 MB` |

Startup and memory targets should not regress while reducing image size.

## Validation Plan

For every Docker optimization experiment:

```bash
docker build -t anubis:optimized .
docker image inspect anubis:optimized
docker history anubis:optimized
docker compose config --quiet
docker run --rm --network none anubis:optimized "Investigate Docker optimization" --source docker-audit
```

Also verify:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 scripts/run_tests.py
```

If standalone packaging is used, add an image-native smoke test that confirms:

- graph bootstrap succeeds
- config files are readable
- source tree is not writable
- no network is required
- non-root user is active

## Rollback Strategy

Keep the current Dockerfile path until the optimized image meets functional and security parity.

Rollback plan:

1. Keep `anubis:local` based on `python:3.13.5-slim-bookworm`.
2. Build optimized image under a separate tag:

```text
anubis:optimized
```

3. Do not replace Compose default until validation passes.
4. If optimized runtime fails, revert Compose image target to `anubis:local`.
5. Keep current digest-pinned Python base as the safe fallback.

## Final Recommendation

The current Docker architecture is secure and simple, but it cannot meet a 70% size reduction through layer cleanup alone. The app contributes only about `1-2 MB`; the base runtime contributes almost everything.

Recommended path:

```text
1. Apply low-risk hygiene.
2. Prototype standalone executable packaging.
3. Run it in a minimal/distroless runtime image.
4. Preserve Compose hardening.
5. Compare against the 37 MB target.
```

If the 70% target is mandatory, pursue standalone packaging. If operational simplicity is more important, keep the current Python slim image and accept that realistic cleanup will be closer to 1-5%.
