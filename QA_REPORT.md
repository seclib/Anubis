# QA_REPORT.md

## Scope

Date: 2026-06-04

Role: QA Engineer and Software Tester

Test target:
- Backend API: `anubis.interfaces.api.app:app`
- Frontend: Vite production build and preview
- Active AI provider: local Ollama
- Repository root: `/home/fatsio/AI/Anubis`

## Environment

- Python backend started with `.venv/bin/python -m uvicorn anubis.interfaces.api.app:app --host 127.0.0.1 --port 8010`.
- Port `8000` was already occupied by an existing process returning `{"status":"ok"}`, so QA used port `8010` to avoid disturbing the user's running process.
- Frontend started with `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`.
- Google Chrome headless was available and used for DOM rendering and screenshot validation.
- Playwright was not installed, so navigation was validated through rendered DOM, HTTP/API calls, and route-surface checks rather than browser click automation.

## Test Summary

| Area | Result | Evidence |
| --- | --- | --- |
| Startup | Passed | Backend reached `Application startup complete`; frontend preview served `http://127.0.0.1:4173/`. |
| Shutdown | Passed | Backend accepted `CTRL+C` and reported `Application shutdown complete`; frontend preview was stopped after QA. |
| UI rendering | Passed | `curl` returned the production HTML; Chrome headless rendered React DOM containing `ANUBIS`, module navigation, chat shell, composer, context panel, and status panes. |
| Navigation | Passed with limitation | Sidebar/module controls rendered; vault navigation/search APIs returned expected data. No Playwright click automation was available. |
| API health | Passed | `/health` returned `{"status":"ok"}` and `/health/ready` returned readiness metadata. |
| Filesystem operations | Passed | `/notes`, `/write`, `/read`, and vault navigation/search worked; path traversal attempts returned HTTP 400. |
| Memory/RAG | Passed | `/embed` succeeded through Ollama; `/rag/reindex`, `/rag/search`, `/memory`, and `/search_rag` returned indexed QA content after reindex. |
| AI providers | Passed with limitation | Ollama `/api/tags` listed 10 models and `/api/generate` returned `QA_OLLAMA_OK`; OpenAI and Anthropic adapters correctly raise "not configured". |
| Local models | Passed | Local Ollama model `qwen2.5-coder:7b` generated a deterministic smoke response. |
| Ollama integration | Passed | Ollama tags and generation endpoints were reachable on `127.0.0.1:11434`. |
| Agent execution | Passed | `/agent/chat` returned an answer grounded in the QA note after indexing. |
| Terminal integration | Failed, fixed, retested passed | See Bug 1. |

## Bug 1: Terminal API Allowed Dangerous Commands

Severity: Critical

Status: Fixed and retested

### Reproduction

1. Start the backend.
2. Create a terminal session:
   - `POST /api/terminal/sessions`
   - Payload: `{"task_id":"qa-break","agent_type":"executor"}`
3. Run dangerous commands through the terminal endpoint:
   - `rm -rf /tmp/qa_should_not_run`
   - `cat /etc/passwd`
   - `python3 -c 'print(123)'`

Before the fix:
- `rm -rf /tmp/qa_should_not_run` returned success with code `0`.
- Inline Python execution returned success.
- The terminal sandbox was relying on role permission and shell metacharacter checks, but it did not inspect executable risk, inline execution flags, or absolute host path arguments.

### Root Cause

The terminal service checked whether an executor role was allowed to use `run_command`, but the command-content policy was incomplete inside `anubis/distributed/sandbox_runtime.py`.

The sandbox already rejected shell control operators like `&&`, `|`, and command substitution, and it executed commands with `shell=False`. However, it still allowed:
- destructive executable names such as `rm`;
- absolute host path arguments such as `/etc/passwd`;
- inline interpreter execution such as `python3 -c`.

This made the integrated terminal meaningfully less isolated than its API and permission naming implied.

### Fix

Changed:
- `anubis/distributed/sandbox_runtime.py`
- `tests/test_terminal_service.py`

Added sandbox command-token validation before `subprocess.run`:
- rejects forbidden executables (`rm`, `sudo`, `dd`, `mkfs`, `docker`, `systemctl`, etc.);
- rejects absolute host paths;
- rejects inline interpreter flags for shells and common runtimes (`bash -c`, `python3 -c`, `node -e`, etc.).

Added regression tests:
- terminal rejects destructive commands;
- terminal rejects absolute host paths;
- terminal rejects inline execution flags;
- existing shell-control regression remains covered.

### Retest

Unit retest:
- `.venv/bin/python -m pytest tests/test_terminal_service.py -q`
- Result: `8 passed`.

Live API retest after backend restart:
- `echo QA_TERMINAL_OK` returned success and output `QA_TERMINAL_OK`.
- `rm -rf /tmp/anubis-nope` returned `success=false`, output `forbidden command: rm`.
- `cat /etc/passwd` returned `success=false`, output `absolute host paths are not allowed: /etc/passwd`.
- `python3 -c 'print(123)'` returned `success=false`, output `inline execution is not allowed for python3`.

## Break Attempts

- Path traversal through note and file APIs:
  - `GET /notes/../../etc/passwd` returned HTTP 400.
  - `POST /read` with `../../etc/passwd` returned HTTP 400.
- Terminal command chaining:
  - `echo safe && echo unsafe` is already rejected by sandbox shell-control checks.
- Long-running terminal command:
  - `sleep 10` was terminated by sandbox timeout behavior.
- Dangerous terminal commands:
  - Initially succeeded for `rm`; now blocked.

## Cleanup

QA-created vault artifacts were removed after validation:
- `vault/qa/qa-test.md`
- `vault/qa/local-write.md`
- `vault/agent-runs/20260604-071515.md`

## Remaining Risks

- Browser click-through navigation is not fully automated because Playwright is not installed in this workspace.
- OpenAI and Anthropic are adapter placeholders, not active provider integrations.
- Port `8000` was already in use by an existing process. The app can start on another port, but development startup scripts should eventually detect and report port conflicts more clearly.
- Terminal policy is now safer, but a production-grade sandbox should also use OS-level isolation beyond subprocess constraints.

## Verification Commands

- `npm run build`
- `.venv/bin/python -m pytest tests/test_terminal_service.py -q`
- `python3 -m py_compile anubis/distributed/sandbox_runtime.py`
- Backend health checks against `http://127.0.0.1:8010/health` and `/health/ready`
- Frontend render checks against `http://127.0.0.1:4173/`
- Ollama tags and generate checks against `http://127.0.0.1:11434`
