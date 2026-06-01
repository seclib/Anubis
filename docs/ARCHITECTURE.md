# Anubis Agent Architecture

For the production Desktop OS folder boundaries and entrypoints, see
`docs/SYSTEM_ARCHITECTURE.md`. This file documents the lower-level autonomous
agent dependency rules.

## Dependency Direction

```text
cli / api / main
  -> runtime
    -> agent
    -> executor
    -> tools
    -> memory
    -> llm
      -> core / config
```

Lower layers never import higher layers.

## Module Tree

```text
agent/
  loop.py              # observe -> plan -> act -> reflect state machine
  dependencies.py      # Protocols consumed by the agent loop
  multi_agent.py       # Agent specs, prompts, roster; no LLM calls
  parser.py            # LLM action parsing
  streaming.py         # Agent event formatting primitives

executor/
  tool_executor.py     # Generic executor; no concrete tools, runtime, memory, LLM, or agent imports

runtime/
  agent_runner.py      # Production entrypoint
  dependencies.py      # Composition root for memory, LLM, tools
  llm_agents.py        # AgentSpec -> stateless LLM client adapter
  plugins.py           # Runtime-owned plugin registration
  router.py            # LLM/tool/final route classification
  streaming.py         # CLI/API streaming adapters
  tool_registry.py     # Concrete tool registry and executor instance

tools/
  *.py                 # Pure tool functions; never import agent

memory/
  state.py             # Short-term run/task memory
  hermes.py            # Long-term memory and Obsidian persistence
  vector.py            # Vector recall/indexing

llm/
  ollama.py            # Stateless provider client
```

## Strict Rules

- `agent` never imports `tools`, `executor`, `memory`, `llm`, or `runtime` as concrete dependencies.
- Non-agent modules never import `agent` at module import time. The composition root may resolve the concrete agent loop and pass it into `AgentRunner`.
- `tools` never import `agent`.
- `executor` never imports `tools`, `runtime`, `memory`, `llm`, or `agent`.
- `memory` never imports `agent` or `runtime`.
- `llm` never imports `agent`, `tools`, `executor`, or `memory`.
- `runtime` is the only layer allowed to assemble concrete implementations.
- Package `__init__.py` files stay empty or metadata-only; they must not eagerly import concrete modules.

## Dependency Injection

All side-effecting services enter the agent through `core.contracts.AgentDependencies`.

```text
AgentRunner(
  agent_loop=<callable>,
  dependency_factory=lambda: AgentDependencies(
    tool_executor=<ToolRunner>,
    memory=<MemoryStore>,
    call_agent=<stateless AgentCaller>,
    vector_context=<callable>,
    hermes_context=<callable>,
  )
)
```

This prevents circular imports because modules depend on stable protocols, not
on each other:

```text
agent.loop -> core.contracts
runtime.dependencies -> core.contracts
executor.tool_executor -> injected tool mapping
llm.ollama -> stateless HTTP client only
```

Concrete wiring is delayed until the composition root. No lower-level module
needs to import the implementation that will call it back.

## Agent Loop

```text
observe
  load short memory
  retrieve long memory
  inspect repository context

plan
  ask planner/orchestrator through injected AgentCaller
  normalize plan and priorities

act
  parse LLM action
  route action as plan/tool/llm/final
  execute tools only through injected ToolRunner

reflect
  verify result
  update short memory
  summarize useful long-term memory
  either continue, fix, replan, or complete
```

## Router

`runtime.router` is stateless. It only classifies parsed actions:

```text
plan   -> update current plan
tool   -> execute registered tool through ToolExecutor
llm    -> continue reasoning
final  -> verify and complete
invalid -> repair action or create dynamic tool
```

## Memory

- Short-term memory is run-local task state in `memory.state`.
- Long-term memory is durable Hermes memory in `memory.hermes`.
- Vector recall is isolated in `memory.vector`.
- The agent accesses memory through `AgentDependencies`, not concrete imports.

## Plugins

Plugins are runtime-owned tool contributors:

```text
plugin -> runtime.plugins.ToolPlugin -> runtime.tool_registry -> executor.ToolExecutor
```

Plugins may register tools. Plugins must not import the agent loop.

## Streaming CLI

The agent loop emits structured progress events. Runtime/CLI adapters format
them for terminal display or HTTP/SSE. The agent loop must not depend on CLI UI.
