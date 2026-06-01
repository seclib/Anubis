# Agent

The agent package owns autonomous and multi-agent behavior.

## Entry Points

- Runtime runner: `runtime.agent_runner.run_agent_loop`
- Multi-agent roster: `agent.multi_agent.AGENT_SPECS`
- Desktop API adapter: `backend.agent.loop.AgentLoop`

## Interface

The production agent boundary is a task/message in, structured result out.
Tools must execute through `executor`/runtime registries rather than importing
agent internals.

## Coupling Rule

Agent modules may depend on stable contracts and injected runtime dependencies.
Tools, RAG, vault, and UI code must not import concrete agent loop internals.
