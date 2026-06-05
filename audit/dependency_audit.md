# ANUBIS Dependency Audit

Audit date: 2026-06-05

## Summary

ANUBIS currently has no required third-party runtime Python dependencies. Runtime code uses the Python standard library only.

Development dependencies are declared in `pyproject.toml` under the optional `dev` extra:

- `pytest>=8.0`
- `pytest-asyncio>=0.23`
- `ruff==0.8.6`

`requirements.txt` intentionally contains comments only.

## Python Packaging

`pyproject.toml`:

- Project name: `anubis`
- Version: `0.1.0`
- Requires Python: `>=3.11`
- Runtime dependencies: `[]`
- Test configuration: `tests`
- Ruff target: `py311`
- Ruff line length: `100`

Runtime container image:

- `python:3.13.5-slim-bookworm`
- Image is pinned by digest in both `Dockerfile` and `docker-compose.yml`.

CI Python version:

- GitHub Actions uses Python `3.13`.

Potential mismatch:

- Package metadata allows Python `>=3.11`.
- Docker and CI use Python `3.13`.
- Existing tracked bytecode files are Python 3.13 cache artifacts.

## External Runtime Dependencies

Verified by `tools/dependency_scanner.py`:

```text
runtime_dependencies: []
pyproject_declares_empty_runtime_deps: True
```

No runtime imports of `requests`, `httpx`, `FastAPI`, `uvicorn`, Redis, Postgres, SQLite, Chroma, FAISS, sentence-transformers, or similar external services were found in source code.

## Development and Test Dependencies

Declared optional tools:

- `pytest`: needed for at least `tests/test_orchestrator.py`, which the custom runner skips.
- `pytest-asyncio`: needed for pytest-native async test execution.
- `ruff`: used in CI lint pipeline for critical checks.

The repository also provides `scripts/run_tests.py`, a standard-library custom runner. It skips `test_orchestrator.py` because that test requires pytest.

## Docker Dependencies

Dockerfile:

- Base: pinned Python slim Bookworm image.
- No package manager install steps.
- No `pip install`.
- Copies `bootstrap.py`, `pyproject.toml`, `requirements.txt`, `src`, `core`, `agents`, and `config`.
- Runs as fixed non-root UID/GID `10001:10001`.
- Makes `/app` read-only at image build time.

Compose:

- Builds from local Dockerfile.
- Uses the same pinned Python image argument.
- Sets resource and security limits.
- Default service uses `network_mode: none`.
- Network-enabled service exists only behind profile `network-enabled`.

## Tauri and Node Dependencies

No Tauri, Node, Rust, or frontend dependencies were found.

Absent files:

- `package.json`
- `package-lock.json`
- `pnpm-lock.yaml`
- `yarn.lock`
- `Cargo.toml`
- `Cargo.lock`
- `tauri.conf.*`
- `vite.config.*`

## Configuration Dependencies

The runtime depends on policy/config files for documented behavior:

- `config/agents.yaml`
- `config/audit_policy.yaml`
- `config/logging.yaml`
- `config/permissions.yaml`
- `config/production_hardening.yaml`
- `config/sandbox.yaml`
- `config/secrets_policy.yaml`
- `config/settings.yaml`

Important note: much of the current code constructs default policies in Python rather than loading these YAML files at runtime. The config files are policy artifacts and validation targets, but they are not uniformly wired into all runtime paths.

## Git and CI Dependencies

GitHub Actions uses external GitHub actions:

- `actions/checkout@v4`
- `actions/setup-python@v5`
- `actions/upload-artifact@v4`
- `github/codeql-action/init@v3`
- `github/codeql-action/analyze@v3`

No automatic deployment actions are present.

## Dependency Risks

- No lockfile exists for dev dependencies; reproducibility relies on version ranges except `ruff`.
- Docker base image digest pins runtime, but Python package metadata is broader than tested runtime.
- The custom test runner skips one pytest-dependent test, so full validation requires pytest in dev environments.
- Tracked bytecode files create dependency-like coupling to CPython version and should not be source-controlled.

## Dependency Conclusion

The runtime dependency posture is excellent for local-first determinism: standard library only, no service dependencies, no network stack dependency, and pinned container image. The main cleanup need is reproducibility hygiene around dev tooling and tracked bytecode, not runtime dependency reduction.
