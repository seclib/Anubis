# Anubis Agent - Autonomous Development Agent

A fully autonomous AI development agent that runs locally with **Ollama**, executing tools autonomously through a state machine reasoning loop.

## Architecture

```
anubis-agent/
├── app/                 # Docker-friendly entrypoints
│   ├── __init__.py
│   └── main.py
├── agent/               # Core orchestration & reasoning
│   ├── __init__.py
│   ├── loop.py         # State machine + main agent loop
│   ├── memory.py       # Persistent state & learning
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
├── main.py            # Entry point
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
1. **Try a solution** → Propose an action using available tools
2. **Observe result** → Capture output, success/failure, errors
3. **Correct if error** → Ask LLM for corrected arguments, retry
4. **Never abandon immediately** → Exhaust all retries, try alternatives
5. **Own the outcome** → Responsible for final task success

### 3. **Automatic Error Recovery**
- Tool failures trigger LLM correction
- Up to 3 retry attempts per tool
- Automatic argument refinement based on error messages

### 4. **Task Validation**
Before completion, the agent validates:
- ✓ All created files exist
- ✓ All commands succeeded
- ✓ Task objective is truly achieved
- If validation fails → Agent continues fixing

### 5. **Memory & Learning**
- Goal tracking
- Step success rate
- Failure history
- Action replay log
- Compact state summaries for LLM

### 6. **Project Introspection**
Automatic detection of:
- Project type (Node, Python, Docker, Go, Rust, Java)
- Framework (React, Vue, Django, Flask, FastAPI, etc.)
- Entry points (main files, scripts, Dockerfile)

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

# Agent behavior
export MAX_STEPS="30"                  # Max loop iterations
export MAX_RETRIES="3"                 # Retry attempts per tool
export MAX_TOOL_RETRIES="3"           # Tool executor retries
export CONTINUOUS_RUN="true"          # Always run without interruption

# OpenAI-compatible API
export API_HOST="127.0.0.1"
export API_PORT="8000"
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

This starts a local OpenAI-compatible backend at:

```text
http://localhost:8000/v1
```

Implemented endpoints:
- `GET /v1/models`
- `POST /v1/chat/completions`
- `GET /health`

Streaming is supported on `POST /v1/chat/completions` with `stream=true`.
Open WebUI can therefore display live agent progress, including:
- state transitions
- tool execution logs
- retry / auto-correction events
- intermediate verification results

### Connecting Open WebUI

In Open WebUI:

1. Go to `Admin Settings`
2. Open `Connections > OpenAI > Manage`
3. Add a new `Standard / Compatible` connection
4. Set `API URL` to `http://localhost:8000/v1`
5. Set `API Key` to `none` or leave it empty if `API_KEY` is not configured
6. Save, then select the model `claude-code-local`

If Open WebUI runs in Docker, use:

```text
http://host.docker.internal:8000/v1
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
