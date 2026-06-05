# ANUBIS

Minimal local-first orchestration core for task routing, agent spawning, state tracking, and lifecycle management.

The current implementation is intentionally small and extensible:

- typed task and lifecycle models
- capability-based agent routing
- async agent runtime with spawn/cancel support
- bounded execution layer with retries, timeouts, rollback hooks, and failure isolation
- sandbox model with capability permissions, isolation profiles, and execution gating
- safety monitor with anomaly detection, suspicious behavior scoring, and kill-switch triggers
- deterministic planning engine with explainable step decomposition
- swarm coordination with role assignment, performance scoring, replacement, and deterministic consensus
- shared memory with scoped isolation, deterministic conflict handling, and vector sync cursors
- retrieval system with embedding pipeline, vector DB abstraction, and scoped/global query routing
- in-memory event bus and state store interfaces
- production-facing boundaries for replacing memory with durable infrastructure later
