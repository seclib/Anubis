# ANUBIS Risk Assessment

Audit date: 2026-06-05

## Overall Risk Rating

Current local prototype risk: Medium.

Production deployment risk: High until runtime ownership, persistence, config authority, and sandbox isolation semantics are clarified.

The project has strong safety intent, good tests, hardened Docker defaults, no runtime third-party dependencies, and no default network. The main risks are not obvious unsafe code paths; they are ambiguity, durability gaps, and possible mismatch between documented controls and active runtime behavior.

## Key Risks

### 1. Runtime Ambiguity

Severity: High

The active CLI/Docker runtime uses `core.graph`, while a richer `src/anubis` living runtime is also tested and exposed through `core/orchestrator`.

Risk:

- Operators and contributors may assume one runtime's guarantees apply to the other.
- Security fixes and behavior changes can diverge.

Mitigation:

- Declare canonical runtime ownership.
- Document which subsystems are production, compatibility, or experimental.
- Add integration tests that assert the intended entrypoint remains canonical.

### 2. Sandbox Overinterpretation

Severity: High

The active graph sandbox authorizes and validates structured task requests. It does not provide per-task OS isolation.

Risk:

- If future task handlers perform real execution, current sandbox semantics may be insufficient.
- Documentation can be read as stronger than implementation.

Mitigation:

- Keep real execution forbidden unless a separate isolated runner is introduced.
- Add explicit docs naming current behavior as authorization and validation.
- For production execution, require process/container isolation and escape tests.

### 3. In-Memory Audit and Memory

Severity: High

Audit logs, memory, vector index, events, metrics, traces, request state, and graph history are in-memory.

Risk:

- No durable forensic record.
- No restart recovery.
- Configured audit retention cannot be enforced.

Mitigation:

- Define durable append-only audit storage.
- Separate runtime memory from persistent memory.
- Add replay/recovery tests once persistence exists.

### 4. Policy Drift

Severity: Medium-High

Config files define hardening policy, but runtime code often constructs defaults directly.

Risk:

- Operators may edit config without affecting runtime.
- Tests may validate text presence rather than live enforcement.

Mitigation:

- Make selected config files authoritative inputs or label them as policy documents.
- Add tests comparing effective runtime settings to config.

### 5. Repository Hygiene Risk

Severity: Medium

Tracked `__pycache__` files create persistent git noise and Python-version coupling.

Risk:

- Verification mutates repository state.
- Reviews include generated artifacts.

Mitigation:

- Remove tracked bytecode in a dedicated cleanup change.
- Ignore pycache and pyc files.

### 6. Python Version Compatibility

Severity: Medium

Package metadata claims Python `>=3.11`; Docker and CI use Python `3.13`.

Risk:

- Undetected incompatibility with Python 3.11 or 3.12.

Mitigation:

- Add CI matrix for declared versions or tighten metadata.

### 7. Partial Test Runner Coverage

Severity: Medium

The custom runner reports 155 passing tests but skips `test_orchestrator.py`.

Risk:

- `make test` is not equivalent to full pytest execution.

Mitigation:

- Convert the skipped test or run pytest in CI.

### 8. No Durable External Service Boundaries

Severity: Medium

There are no databases, queues, vector DBs, external model services, or network integrations.

Risk:

- Low integration attack surface today, but future integrations may be added without established adapter contracts.

Mitigation:

- Define adapter interfaces and security gates before adding external services.

### 9. CI Supply Chain Risk

Severity: Low-Medium

GitHub workflows use versioned actions by tag, not digest.

Risk:

- Tag-based action references are less strict than digest pinning.

Mitigation:

- Pin critical actions by SHA for higher assurance environments.

### 10. Docker Base Image Freshness

Severity: Low-Medium

The Docker base image is pinned by digest, which is good for reproducibility but requires deliberate updates.

Risk:

- Security updates are not picked up automatically.

Mitigation:

- Add a scheduled review process for base image digest updates.

## Security Posture

Strengths:

- Deny-by-default policy intent.
- No runtime third-party dependencies.
- Default Docker network disabled.
- Non-root container user.
- Read-only root filesystem.
- Dropped Linux capabilities.
- `no-new-privileges`.
- Sandbox and permission tests pass.
- Code scanning and hardening validation exist.
- Auto-refactor is proposal-only.
- No automatic production deployment workflow found.

Limitations:

- Audit and kill-switch state are process-local.
- Application config is not uniformly authoritative.
- Per-task isolation is not implemented in active graph runtime.
- No full secret scanning tool beyond project-specific policy checks was run in this audit.

## Operational Risk

Local CLI use:

- Low to Medium risk.
- Fast deterministic runs.
- Minimal dependency and network surface.

Hardened container use:

- Medium risk.
- Container hardening is strong, but runtime state remains ephemeral.

Production use:

- High risk without additional work.
- Missing durable state, canonical runtime clarity, authoritative config loading, and production-grade task isolation.

## Risk Conclusion

ANUBIS is well positioned as a deterministic local-first orchestration framework, but it is not yet production-ready in the operational sense. The next risk-reduction work should focus on clarity and controls: one canonical runtime, explicit sandbox semantics, durable audit/memory storage, config authority, and repository hygiene.
