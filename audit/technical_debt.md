# ANUBIS Technical Debt Audit

Audit date: 2026-06-05

## Highest Priority Debt

### 1. Split Runtime Ownership

The repository has two overlapping architectures:

- `core/*`: active deterministic graph runtime.
- `src/anubis/*`: living-loop runtime with richer subsystems.

Duplicated concepts include orchestrator, planner, agents, execution, sandbox, memory, retrieval, plugins, swarm, observability, safety, and audit.

Impact:

- Harder to know which implementation is canonical.
- More tests and docs can pass while production behavior differs.
- Bug fixes may land in one layer and not the other.

Recommended direction:

- Declare one canonical runtime contract.
- Treat the other layer as compatibility, experimental, or migration code.
- Create a boundary map before deleting or merging anything.

### 2. Tracked Bytecode Files

The repository contains many tracked `__pycache__/*.pyc` files. Running compile or tests mutates them and pollutes git status.

Impact:

- Verification creates noisy diffs.
- Python version becomes implicitly encoded in the repository.
- Review signal gets worse.

Recommended direction:

- Stop tracking bytecode files.
- Add or confirm `.gitignore` coverage for `__pycache__/` and `*.pyc`.
- Remove tracked pycache artifacts in a dedicated cleanup change.

### 3. Policy Files Are Not Uniform Runtime Inputs

The repository has strong YAML policies under `config/`, but many runtime paths construct policy defaults directly in Python.

Impact:

- Config can drift from runtime behavior.
- Hardening docs can pass validation without fully controlling the application.
- Operators may assume YAML edits change behavior when they do not.

Recommended direction:

- Add explicit config loading or document files as policy attestations only.
- Test that runtime defaults match config values where config is intended to be authoritative.

### 4. In-Memory-Only Persistence

Memory, retrieval vectors, audit logs, events, traces, metrics, plugin state, graph state history, and request state are all in-memory.

Impact:

- No restart durability.
- No forensic retention outside a single process.
- Configured audit retention is not enforceable in the current runtime.

Recommended direction:

- Decide which stores must remain ephemeral.
- Define a durable storage abstraction for audit, memory, and graph run history before production use.

### 5. Sandbox Naming Versus Isolation Semantics

The active `core` sandbox path validates tasks and prevents direct execution, but it does not run tasks in a separate process, chroot, namespace, or container. Docker hardening provides process isolation for the whole app, not per-task isolation.

Impact:

- The term sandbox may imply stronger execution isolation than currently exists.
- Future real task execution would need a stronger runner boundary.

Recommended direction:

- Keep current validation boundary for simulated execution.
- Rename or document it as an authorization sandbox unless per-task isolation is added.
- If real task execution is introduced, implement process/container isolation and tests for escape controls.

## Medium Priority Debt

### Custom Test Runner Skips Pytest-Only Test

`scripts/run_tests.py` skips `test_orchestrator.py` because it requires pytest.

Impact:

- CI's standard-library runner does not execute every test file.
- Local `make test` does not prove full pytest parity.

Recommended direction:

- Either convert the skipped test to the custom runner pattern or make pytest the canonical test runner for dev/CI.

### Broad Modules Need Decomposition

Several modules exceed 300 lines and hold many responsibilities:

- `src/anubis/swarm.py`
- `src/anubis/memory.py`
- `src/anubis/plugins.py`
- `core/graph/runner.py`
- `src/anubis/planner.py`

Impact:

- Higher review burden.
- More difficult targeted testing.
- Larger blast radius for changes.

Recommended direction:

- Decompose only after runtime ownership is clarified.
- Avoid premature refactors that duplicate the existing split.

### README Overstates or Blurs Active Structure

The README describes the production graph accurately, but it also presents some modules as top-level production pillars even where actual active usage is narrower or implementation is split.

Impact:

- New contributors may follow docs into the wrong layer.

Recommended direction:

- Add "active entrypoint" and "experimental/secondary runtime" sections.

### Dev Dependency Reproducibility

Runtime dependencies are empty, but dev dependencies are not locked except Ruff.

Impact:

- Pytest behavior can vary across environments.

Recommended direction:

- Pin or lock dev dependencies if deterministic CI remains a project goal.

### No Tauri or Frontend Despite Audit Scope

The project has no Tauri files or frontend manifests.

Impact:

- Any Tauri expectations are external to the current repository state.

Recommended direction:

- Document "not present" rather than leaving ambiguity.

## Lower Priority Debt

### CI Metadata Duplication

Declarative workflow summaries exist under `ci/` and executable workflows exist under `.github/workflows/`.

Impact:

- Possible drift between summaries and actual workflows.

Recommended direction:

- Treat `ci/` files as documentation and validate them against workflow names, or remove them if not needed.

### Mixed Python Version Signals

`pyproject.toml` declares `>=3.11`, Ruff targets `py311`, but CI and Docker use Python 3.13.

Impact:

- Code may accidentally rely on Python 3.13 while claiming 3.11 compatibility.

Recommended direction:

- Test 3.11 explicitly or raise the declared minimum to the actual supported version.

### No Benchmark Harness

There is no formal benchmark suite.

Impact:

- Performance regressions will be anecdotal.

Recommended direction:

- Add lightweight benchmark commands only after defining expected workloads.

## Technical Debt Conclusion

The project is not suffering from dependency sprawl or missing tests. Its main debt is architectural duplication and operational maturity: two runtime models, in-memory stores, and policy/runtime drift. Cleanup should start with ownership and repository hygiene, not feature work.
