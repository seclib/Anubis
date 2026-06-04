# Anubis Code Architecture

## Runtime Shape

`CLI/Desktop/API -> SessionRuntime -> AgentOrchestrator -> OllamaRouter + ToolExecutionEngine + SessionMemory`

Critical modules:

- `anubis.core.session.SessionRuntime`: one local session turn, streamed as typed events.
- `anubis.core.session.AgentOrchestrator`: planner, executor, reviewer orchestration.
- `anubis.core.session_events.SessionEvent`: single event envelope for CLI, SSE, and desktop.
- `anubis.llm.ollama.OllamaRouter`: local model routing for fast, code, and review turns.
- `anubis.tools.session_tools`: filesystem and shell tools for local Linux work.
- `anubis.memory.session.SessionMemory`: short-term transcript, facts, and tool history.
- `anubis.cli.terminal.TerminalRenderer`: Claude-Code-style live terminal rendering.

## Terminal UX

Natural language starts an agent turn. Slash commands remain reserved for shell-like control:

- `/help`, `/status`, `/exit`
- `/memory`, `/compact`
- `/tools`
- `/agents`, `/swarm`

Each turn should show:

1. selected model
2. short plan
3. recalled memory count
4. visible tool calls
5. streamed assistant output
6. final done marker

## Tool Calling

Tools are the only place where side effects happen. Prompts may request a tool, but the runtime executes it and emits `tool.request`, `tool.result`, or `tool.error`.

Safe tools:

- `read_file`
- `list_files`

Confirm or restrict by policy:

- `write_file`
- `run_shell`

Blocked by default:

- destructive shell commands
- privilege escalation
- path traversal outside the project root

## Memory

Session memory is split into transcript, durable facts, and tool history. Long-term Qdrant or Obsidian memory should be attached behind the same `retrieve` and `remember` boundary instead of being called directly from agents.

## Multi-Agent Rules

Keep the canonical roles small:

- planner: decides the path
- executor: selects tools or final response
- reviewer: verifies result and risk

Use swarm only for large tasks. Orchestration and memory are platform services, not separate reasoning agents.

## Anti-Patterns To Avoid

- one huge agent loop owning prompts, tools, memory, streaming, retries, and UI
- parsing terminal output as program state
- letting prompts perform side effects without tool events
- mixing OpenAI-compatible token chunks with internal agent progress events
- global mutable memory with no session boundary
- unbounded shell access
- hidden tool calls that the terminal cannot display
- adding more agent roles instead of improving routing and context
