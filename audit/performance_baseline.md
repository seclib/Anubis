# ANUBIS Performance Baseline

Audit date: 2026-06-05

## Baseline Environment

Working directory:

```text
/home/fatsio/AI/Anubis
```

Observed runtime:

- Python commands executed with system `python3`.
- Docker Compose configuration validation available and passing.
- Runtime dependencies: standard library only.

## Repository Size Baseline

- Python files: 204
- Total Python lines: 18,831
- Source files under `core` and `src`: 159
- Test files at top-level `tests/test_*.py`: 31

Largest Python modules:

| Lines | File |
| ---: | --- |
| 609 | `src/anubis/swarm.py` |
| 600 | `src/anubis/memory.py` |
| 499 | `src/anubis/plugins.py` |
| 439 | `core/graph/runner.py` |
| 407 | `src/anubis/planner.py` |
| 396 | `src/anubis/__init__.py` |
| 356 | `src/anubis/self_improvement.py` |
| 356 | `src/anubis/architecture.py` |
| 350 | `src/anubis/audit.py` |
| 338 | `core/orchestrator/orchestrator.py` |

## Verification Baseline

### Compile

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q bootstrap.py core src agents tests tools scripts
```

Result: passed.

### Custom Test Runner

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 scripts/run_tests.py
```

Result:

- Passed: 155 tests
- Skipped: `test_orchestrator.py` because it requires pytest
- Failures: 0

### Security and Hardening Tools

Command:

```bash
PYTHONPATH=src:. python3 tools/dependency_scanner.py
PYTHONPATH=src:. python3 tools/code_analyzer.py
PYTHONPATH=src:. python3 tools/sandbox_tester.py
python3 tools/hardening_validator.py
```

Result: passed.

Observed tool outputs:

- Runtime dependencies: `[]`
- `pyproject.toml` declares empty runtime dependencies: `True`
- Source scan found 159 Python files under `src` and `core`
- Largest source file by the scanner: `src/anubis/swarm.py`
- Sandbox probe denied missing capability as expected
- Hardening policy reported valid

### Docker Compose Config

Command:

```bash
docker compose config --quiet
```

Result: passed.

## Bootstrap Performance Baseline

Command:

```bash
/usr/bin/time -p python3 bootstrap.py "Investigate audit baseline anomaly" --source audit
```

Wall-clock result:

```text
real 0.26
user 0.22
sys 0.03
```

Bootstrap output summary:

- Status: completed
- Request count: 1
- Result count: 1
- Succeeded: true
- Execution path: `input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output`
- Task count: 3
- State history entries: 10
- State transitions: 10
- Errors: 0
- Memory after run:
  - episodic records: 1
  - semantic records: 1
  - vector records: 2
- Reflection:
  - task count: 3
  - completed tasks: 3
  - success rate: 1.0
  - score: 1.0

## Resource Baseline

Docker Compose runtime limits:

- CPUs: `1.0`
- Memory: `512m`
- Swap: `512m`
- PID limit: `128`
- nofile soft/hard: `1024`
- nproc: `128`
- Writable tmpfs: `/tmp`, 16 MB, `noexec,nosuid,nodev`
- Root filesystem: read-only
- Default network: none

Application sandbox policy:

- Timeout: 30 seconds in config policy
- Memory metadata limit: 256 MB in config policy
- Network default: denied
- Filesystem default: sandbox-only

Living runtime execution policy:

- Retry max attempts: 2
- Timeout: 5 seconds in `build_runtime()`

## Performance Observations

- The active graph runtime is very fast for the default deterministic workload.
- Current memory, retrieval, logs, traces, audit, and state history are in-memory, so startup and tests are lightweight.
- Retrieval uses deterministic hashing embeddings and in-memory cosine scoring, so it avoids model latency and external vector DB overhead.
- There is no load test, concurrency test, benchmark suite, memory profile, or long-running stability metric.
- The custom test runner completed quickly in this environment, but it is not a substitute for pytest collection parity because one pytest-dependent test is skipped.

## Baseline Conclusion

The current runtime baseline is small and fast for deterministic local orchestration. Performance risk is low for single-run CLI use and high for any future durable, concurrent, or large-memory workload because the current architecture stores nearly everything in memory and has no persistence or indexing beyond simple append-only lists.
