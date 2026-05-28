# Anubis - Autonomous Development Agent

A fully autonomous AI development agent that runs locally with **Ollama**, executing tools autonomously through a state machine reasoning loop.

## Architecture

```
anubis-agent/
├── app/                # FastAPI OpenAI-compatible API
│   ├── __init__.py
│   └── main.py         # FastAPI app + Open WebUI compatibility
├── agent/               # Core orchestration & reasoning
│   ├── __init__.py
│   ├── loop.py         # State machine + main agent loop
│   ├── memory.py       # Persistent state & learning
│   ├── multi_agent.py  # Multi-agent roles, prompts, and Ollama model routing
│   ├── parser.py       # JSON action parser
│   ├── planner.py      # Task planning
│   └── prompts.py      # System prompts
├── llm/                # Language model interface
│   ├── __init__.py
│   └── ollama.py       # Ollama integration
├── tools/              # System tools
│   ├── __init__.py
│   ├── filesystem.py   # File operations
│   ├── terminal.py     # Command execution
│   └── repo.py         # Repository introspection
├── executor/           # Tool execution engine
│   ├── __init__.py
│   └── tool_executor.py# Execution + auto-retry + error correction
├── state/              # Persistent state
│   └── runtime.json    # Agent state & memory
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py            # Legacy CLI entry point
├── config.py          # Configuration
└── README.md          # This file
```

## Key Features

### 1. **Autonomous Reasoning Loop**
- **INIT** → **PLAN** → **EXECUTE** → **VERIFY** → **FIX** → **COMPLETE**
- Continuous execution without human intervention
- State-machine driven decision making

### 2. **Global Agent Rules (GARs)**
The agent MUST ALWAYS:
1. **Always try to solve the task** → Choose the safest available tool action and execute it
2. **Never ask for human help** → Do not request confirmation, clarification, or manual intervention
3. **Observe result** → Capture output, success/failure, errors
4. **Correct its own errors** → Analyze failures, change arguments, retry, and switch strategy
5. **Continue until success or total blockage** → Exhaust retries and alternatives before blocking
6. **Own the outcome** → Responsible for final task success

### 3. **Automatic Error Recovery**
- Tool failures trigger LLM correction
- Up to 3 retry attempts per tool
- Automatic argument refinement based on error messages

### 4. **Autonomous Multi-Agent System**
Anubis runs a collaborative team of specialized agents:

- `orchestrator_agent`: main brain; receives the user task, distributes work, coordinates steps, aggregates results, and manages retries/priorities
- `planner_agent`: decomposes work into concrete execution steps
- `coder_agent`: modifies code, creates files, refactors, and implements features with minimal clean changes; recommended model `deepseek-coder-v2`
- `reviewer_agent`: acts as a critical senior engineer; reviews generated code, detects potential bugs, verifies architecture quality, and proposes improvements
- `tester_agent`: executes tests, runs validation commands, detects runtime errors, analyzes shell output, and returns structured validation reports
- `debugger_agent`: autonomously analyzes stack traces, identifies probable causes, proposes corrections, and reruns fixes
- `memory_agent`: summarizes collaboration and keeps shared context compact

Each agent has:
- a dedicated role
- a specialized prompt
- a dedicated Ollama model configured by environment variable

The agents collaborate through shared runtime memory (`agent_messages` and `collaboration_summary`) and emit live events during streaming.

### 5. **Task Validation**
Before completion, the agent validates:
- ✓ All created files exist
- ✓ All commands succeeded
- ✓ Task objective is truly achieved
- If validation fails → Agent continues fixing

### 6. **Memory & Learning**
- Goal tracking
- Step success rate
- Failure history
- Action replay log
- Compact state summaries for LLM
- Multi-agent collaboration transcript and summary

### 7. **Local Vector Memory / Repository RAG**
- Indexes repository files into a local vector store
- Supports semantic search over code and documentation
- Retrieves relevant context for analysis, coding, review, and debugging prompts
- Indexes agent action history for cross-agent recall
- Uses Ollama embeddings with `bge-m3` by default; `nomic-embed-text` is also supported
- Stores vectors locally in `state/vector_store.json`

### 8. **Project Introspection**
Automatic detection of:
- Project type (Node, Python, Docker, Go, Rust, Java)
- Framework (React, Vue, Django, Flask, FastAPI, etc.)
- Entry points (main files, scripts, Dockerfile)

### 9. **Autonomous Git System**
- Runs validation commands before creating commits
- Creates an automatic commit after successful task verification
- Generates a deterministic commit message from the task and changed files
- Supports optional temporary branches for isolated autonomous runs
- Records commit history locally and can rollback the last autonomous commit
- Aborts commits when validation fails to avoid committing broken work

## Module Responsibilities

### `agent/`
- **loop.py**: Main execution loop, state transitions
- **memory.py**: Persistent memory with statistics
- **prompts.py**: System prompts for LLM
- **parser.py**: JSON action parsing
- **planner.py**: Task decomposition

### `llm/`
- **ollama.py**: Ollama API integration (local, no API keys)

### `tools/`
- **filesystem.py**: read_file, write_file, list_files
- **terminal.py**: run_command (bash/shell execution)
- **repo.py**: scan_full_repo, detect_project_type, detect_framework, detect_entrypoints

### `executor/`
- **tool_executor.py**: Execution engine with auto-retry, error detection, LLM correction

### `state/`
- **runtime.json**: Agent state, task history, completion status

## How It Works

```
User provides task
        ↓
agent/loop.py runs autonomous loop
        ↓
LLM decides next action (plan/act/fix/final)
        ↓
executor/ executes tool if "act" or "fix"
        ↓
Tool fails? → LLM proposes correction → Retry automatically
        ↓
Tool succeeds? → Validate result
        ↓
Validation passes? → Go to next step or complete
        ↓
Validation fails? → Request fix → Continue loop
        ↓
Task complete or max steps reached
```

## Configuration

Set environment variables to customize behavior:

```bash
# LLM
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="mistral"          # or llama2, neural-chat, etc.
export LLM_TEMPERATURE="0.7"
export LLM_MAX_TOKENS="2000"
export PROJECT_ROOT="$(pwd)"           # Workspace root
export EMBEDDING_MODEL="bge-m3"         # or nomic-embed-text
export VECTOR_STORE_FILE="state/vector_store.json"

# Multi-agent Ollama models
export ORCHESTRATOR_AGENT_MODEL="$OLLAMA_MODEL"
export PLANNER_AGENT_MODEL="$OLLAMA_MODEL"
export CODER_AGENT_MODEL="deepseek-coder-v2"
export REVIEWER_AGENT_MODEL="$OLLAMA_MODEL"
export TESTER_AGENT_MODEL="$OLLAMA_MODEL"
export DEBUGGER_AGENT_MODEL="qwen2.5-coder"
export MEMORY_AGENT_MODEL="$OLLAMA_MODEL"

# Agent behavior
export MAX_STEPS="30"                  # Max loop iterations
export MAX_RETRIES="3"                 # Retry attempts per tool
export MAX_TOOL_RETRIES="3"           # Tool executor retries
export CONTINUOUS_RUN="true"          # Always run without interruption

# Autonomous Git
export AUTO_GIT_COMMIT_ENABLED="true" # Commit automatically after verified success
export GIT_VALIDATION_COMMANDS="python3 -m unittest discover -s tests"
export GIT_USE_TEMP_BRANCH="false"    # Set true to commit on temporary branches
export GIT_TEMP_BRANCH_PREFIX="anubis/auto"

# OpenAI-compatible API
export API_HOST="127.0.0.1"
export API_PORT="8000"
export API_BASE_PATH="/v1"
export API_AUTH_REQUIRED="false"
export API_MODEL_ID="claude-code-local"
export API_MODEL_NAME="Claude Code Local Agent"
export API_KEY=""                     # Optional

# Debugging
export LOG_LEVEL="INFO"                # DEBUG, INFO, WARNING, ERROR
export DEBUG="false"
```

## Usage

### Running the Agent

```python
from agent import run_agent_loop

task = "Create a Python script that calculates Fibonacci numbers"
result = run_agent_loop(task)
print(result)
```

### Running the OpenAI-Compatible API

```bash
python3 main.py serve
```

This starts the FastAPI backend at:

```text
http://localhost:8000/v1
```

Implemented endpoints:
- `GET /v1/models`
- `GET /v1/models/{model_id}`
- `POST /v1/chat/completions`
- `POST /v1/agent/stream`
- `GET /health`

`API_BASE_PATH` can be changed if you want Open WebUI to point at a custom base URL path, for example `/openai/v1`.
`API_AUTH_REQUIRED` defaults to `false`, so Open WebUI can connect without any API key.

Streaming is supported on `POST /v1/chat/completions` with `stream=true`.
Open WebUI can therefore display live agent progress, including:
- state transitions
- tool execution logs
- retry / auto-correction events
- intermediate verification results

For a Cursor / Claude Code style UI, use the native structured stream:

```bash
curl -N http://localhost:8000/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"task":"Inspect the repository and summarize the entrypoints"}'
```

This endpoint returns Server-Sent Events:
- `agent_progress`: state, selected action, tool start/result/error, intermediate result, verification
- `agent_result`: final agent result
- `agent_error`: execution error
- `agent_done`: stream closed cleanly

RAG tools available to agents:
- `index_repository`: refresh the local vector index
- `semantic_search`: search indexed repository and agent history semantically
- `retrieve_context`: return prompt-ready relevant context

Git tools available to agents:
- `git_status`: inspect branch and working-tree changes
- `generate_commit_message`: produce an intelligent commit message
- `run_git_validations`: run configured validation before committing
- `autonomous_git_commit`: validate, stage, and commit safe changes
- `rollback_last_autonomous_commit`: revert or hard-reset the last autonomous commit

### Connecting Open WebUI

With Docker Compose, Open WebUI is started and preconfigured automatically:

```bash
docker compose up --build
```

Open the UI at:

```text
http://localhost:3000
```

The bundled Open WebUI service is configured in OpenAI-compatible mode with:
- Base URL inside Docker: `http://anubis-agent:8000/v1`
- Browser/host Base URL: `http://localhost:8000/v1`
- API key: `ignored`
- Model: `claude-code-local`

If you configure an existing Open WebUI manually:

1. Go to `Admin Settings`
2. Open `Connections > OpenAI > Manage`
3. Add a new `Standard / Compatible` connection
4. Set `API URL` to `http://localhost:8000/v1` or your custom `API_BASE_PATH`
5. Set `API Key` to `ignored` unless you explicitly enable `API_AUTH_REQUIRED=true`
6. Save, then select the model `claude-code-local`

If Open WebUI runs in Docker, use:

```text
http://anubis-agent:8000/v1
```

## Docker

Build and run the containerized agent:

```bash
docker compose up --build
```

The container:
- mounts the repository at `/workspace`
- uses `/workspace` as the project root
- reaches Ollama through `http://host.docker.internal:11434`
- exposes the OpenAI-compatible API on `http://localhost:8000/v1`
- exposes Open WebUI on `http://localhost:3000`
- supports Open WebUI streaming via `stream=true`
- allows changing the API path with `API_BASE_PATH`
- keeps auth disabled unless `API_AUTH_REQUIRED=true`

If your local UID/GID is not `1000`, export `UID` and `GID` before building so the workspace mount stays writable.

### Checking Memory

```python
from agent import load_memory, get_task_state_summary

memory = load_memory()
summary = get_task_state_summary(memory)
print(summary)
```

## Requirements

- Python 3.8+
- Ollama (local LLM server)
- Docker 24+ for the containerized workflow
- Python runtime dependency: `requests` (declared in `requirements.txt`)

## Starting Ollama

```bash
# Download a model (first time)
ollama pull mistral    # or llama2, neural-chat, etc.

# Start Ollama server
ollama serve
```

## Design Philosophy

**Autonomous & Resilient**: The agent never gives up. It tries, observes, corrects, and retries until success.

**Local & Private**: Uses Ollama exclusively—no cloud, no API keys, all data stays local.

**Minimal Dependencies**: Core functionality stays lean and uses only `requests` beyond the standard library.

**Responsible**: The agent owns the outcome and validates completion before stopping.

---

**Status**: V4 Architecture - Production Ready
