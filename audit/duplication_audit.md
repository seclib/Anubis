# ANUBIS Dead-Code and Duplication Audit

Audit date: 2026-06-05

## Classification Legend

- `KEEP`: keep as-is; duplication is intentional or the file is active and well-scoped.
- `MERGE`: combine duplicate implementations behind one canonical interface.
- `REFACTOR`: keep behavior but split, rename, document, or make ownership clearer.
- `DEPRECATE`: keep temporarily as a compatibility or experimental surface, but mark non-canonical.
- `REMOVE`: delete after confirmation because it appears unused, obsolete, generated, or redundant.

## Executive Summary

ANUBIS has broad duplication across two runtime families:

- `core/*`: active graph/bootstrap runtime used by `bootstrap.py`.
- `src/anubis/*`: richer living-loop runtime used by tests and by `core/orchestrator`.

Most duplication is architectural rather than accidental copy-paste. The same concepts exist in both families: agents, orchestrators, planners, memory, retrieval, execution, sandboxing, security, plugins, observability, swarm coordination, and audit.

There are also several alias-only modules and lifecycle stubs that are not referenced by active bootstrap or tests. These are the strongest dead-code candidates.

No standalone prompt files or prompt registry were found. “Prompt duplication” exists only as repeated deterministic planning templates, agent messages, and explanatory strings.

## Duplicate Modules and Services

| Finding | Files | Classification | Rationale |
| --- | --- | --- | --- |
| Production graph runtime vs living-loop runtime | `core/graph/*`, `core/bootstrap/*`, `src/anubis/core_life/living_loop.py`, `src/anubis/life_cycle/boot_sequence.py` | `REFACTOR` | Both represent end-to-end orchestration. `core.graph` is active CLI/Docker path; living loop is richer and test-covered. Keep both short-term, but document canonical ownership. |
| Duplicate orchestrator services | `core/orchestrator/orchestrator.py`, `src/anubis/orchestrator.py` | `MERGE` | Both manage user/task orchestration, request state, and execution routing. `core/orchestrator` wraps living runtime; `src/anubis/orchestrator` is async task orchestrator. Define one orchestration API. |
| Duplicate planner services | `core/planner/*`, `src/anubis/planner.py`, `src/anubis/core_life/brain/cognitive_loop.py`, `src/anubis/core_life/metabolism/task_digestion.py` | `MERGE` | `core/planner` builds graph tasks; `src/anubis/planner` builds async plans from templates; cognitive loop and digestion add adjacent planning steps. Consolidate planning contracts and keep adapters if needed. |
| Duplicate execution services | `core/execution/sandbox_runner.py`, `core/execution/executor.py`, `src/anubis/execution.py` | `MERGE` | Graph execution is validation-only; living execution handles retries, timeout, rollback, and events. These should share a single execution policy model. |
| Compatibility execution aliases | `core/execution/error_handler.py`, `core/execution/resource_limits.py`, `core/execution/sandbox.py`, `core/execution/executor.py` | `DEPRECATE` | These mostly re-export `anubis.*` classes. Useful during migration, but they obscure the canonical execution package. |
| Duplicate sandbox/security services | `core/security/*`, `src/anubis/sandbox.py`, `src/anubis/safety.py`, `src/anubis/core_life/immune_system/*` | `MERGE` | Security kernel, sandbox guard, permission system, safety monitor, immune-system aliases, and kill-switch concepts overlap. Keep `core/security` as canonical candidate. |
| Duplicate plugin systems | `core/plugins/*`, `src/anubis/plugins.py` | `MERGE` | Both define plugin manifests, registry, lifecycle, dependency resolution, status, and execution controls. `core/plugins` is graph-era and manifest-focused; `src/anubis/plugins.py` is async/event-rich. |
| Duplicate observability systems | `core/observability/*`, `src/anubis/observability/*` | `MERGE` | Both define logs, traces, metrics, and dashboards. `core` version is more complete; `src/anubis` version has lightweight schemas. |
| Duplicate swarm services | `core/swarm/*`, `src/anubis/swarm.py`, `src/anubis/core_life/swarm/*`, `src/anubis/core_life/swarm_body/*` | `MERGE` | Three swarm abstractions exist: core deterministic coordinator, living runtime swarm coordinator, and research hive. They need explicit boundaries or one common interface. |
| Duplicate audit concepts | `core/security/audit_logger.py`, `src/anubis/audit.py`, `config/audit_policy.yaml` | `MERGE` | Audit policy, hash-chain audit logger, and self-audit/tamper tooling are split. Define a single audit record and storage contract. |
| Duplicate state concepts | `core/graph/state.py`, `core/graph/state_engine.py`, `core/orchestrator/state_manager.py`, `src/anubis/state.py`, `src/anubis/types.py` | `REFACTOR` | Graph state, task state, event types, and compatibility state manager overlap. Keep graph state distinct, but reduce alias/facade ambiguity. |
| Duplicate bootstrap/demo entrypoints | `bootstrap.py`, `core/bootstrap/bootstrap.py`, `core/bootstrap/ultra_light.py`, `src/anubis/bootstrap.py`, `src/anubis/life_cycle/boot_sequence.py` | `REFACTOR` | `bootstrap.py` and `core/bootstrap` are active. `src/anubis/bootstrap.py` is a demo birth point with no inbound imports. |

## Duplicate Memory Systems

| Finding | Files | Classification | Rationale |
| --- | --- | --- | --- |
| Core append-only memory manager vs living shared memory | `core/memory/memory_manager.py`, `src/anubis/memory.py` | `MERGE` | Both implement memory storage and retrieval-adjacent behavior. `src/anubis/memory.py` has stronger scope/sensitivity/conflict controls; `core/memory` has clearer graph integration. |
| Multiple episodic memory implementations | `core/memory/episodic.py`, `src/anubis/core_life/memory_life/episodic_memory.py` | `MERGE` | Both represent execution episodes. The living version subclasses `SharedMemory`; the core version is append-only and graph-integrated. |
| Multiple semantic memory implementations | `core/memory/semantic.py`, `core/memory/semantic_vector_store.py`, `src/anubis/core_life/memory_life/semantic_memory.py` | `MERGE` | Semantic facts, semantic memory, and semantic vector storage are split. Consolidate semantic record shape and retrieval indexing. |
| Short-term/long-term memory layering | `core/memory/short_term.py`, `core/memory/long_term.py`, `core/memory/memory_system.py`, `src/anubis/memory.py` | `REFACTOR` | `core/memory/memory_system.py` cleanly separates layers, while `SharedMemory` encodes scope/kind/sensitivity. Keep both ideas, merge contracts. |
| Duplicate vector/RAG embeddings | `core/memory/vector_store.py`, `core/memory/retriever.py`, `src/anubis/retrieval.py` | `MERGE` | `Embedding`, `HashingEmbedder`, `RetrievalQuery`, and `RetrievalResponse` are duplicated. The deterministic hashing strategy is the same. |
| Memory-life helper modules | `src/anubis/core_life/memory_life/compression_engine.py`, `identity_memory.py`, `recall_policy.py` | `REFACTOR` | These are small domain helpers. `compression_engine.py` is used by `SleepCycle`; identity and recall policy appear unreferenced. |

## Duplicate Agent Logic

| Finding | Files | Classification | Rationale |
| --- | --- | --- | --- |
| Core stateless agents vs living agents | `core/agents/*`, `src/anubis/agents_life/*` | `MERGE` | Both expose planner/analyst/executor-like responsibilities, but with different contracts: synchronous structured dicts vs async task handlers. Consolidate around one agent descriptor and run-result model. |
| Core research-ish agent names vs top-level research agents | `core/agents/planner_agent.py`, `core/agents/analyst_agent.py`, `core/agents/critic_agent.py`, `agents/planner_agent.py`, `agents/analyst_agent.py`, `agents/critic_agent.py` | `REFACTOR` | Names overlap but purposes differ. Top-level `agents/` are research hive agents. Rename/package to make this explicit. |
| Executor duplication | `core/agents/executor_agent.py`, `src/anubis/agents_life/executor_agent.py`, `agents/executor_agent.py` | `MERGE` | Three executor concepts exist: sandbox request preparation, defensive response recommendation, and research action simulation. Keep roles, but separate names and shared contracts. |
| Agent registries | `core/agents/registry.py`, `src/anubis/agents.py`, `src/anubis/core_life/swarm/agent_registry.py` | `MERGE` | Three registries track agents for graph, task runtime, and research swarm. These need a common descriptor vocabulary. |
| Agent descriptors | `core/agents/base_agent.py`, `src/anubis/types.py`, `src/anubis/core_life/swarm/agent_registry.py` | `MERGE` | `AgentDescriptor` exists in more than one shape. This creates integration friction. |
| Top-level research agents | `agents/*` | `KEEP` | These are used by `src/anubis/life_cycle/boot_sequence.py` and research swarm tests. They are not dead code, but the package name is too generic. |

## Duplicate Prompts and Templates

| Finding | Files | Classification | Rationale |
| --- | --- | --- | --- |
| No prompt registry or prompt files | Repository-wide | `KEEP` | No `.prompt`, prompt library, or provider prompt templates were found. There is no prompt subsystem to remove. |
| Repeated planning templates and explanatory messages | `core/planner/planner.py`, `src/anubis/planner.py`, `agents/planner_agent.py`, `core/graph/nodes.py`, `src/anubis/core_life/living_loop.py` | `REFACTOR` | These are deterministic task templates and human-readable explanations, not LLM prompts. They should be centralized only if they become operator-facing policy text. |
| Capability promise text | `src/anubis/capabilities.py`, `README.md`, `docs/*` | `REFACTOR` | Capability descriptions and documentation overlap. Keep docs, but avoid treating capability prose as runtime truth unless validated. |

## Unused or Obsolete File Candidates

These are candidates, not automatic delete recommendations. Some may exist as planned architectural placeholders.

| File | Classification | Evidence |
| --- | --- | --- |
| `src/anubis/bootstrap.py` | `DEPRECATE` | Demo entrypoint with no inbound imports. Active repository entrypoint is top-level `bootstrap.py`. |
| `core/api/middleware.py` | `DEPRECATE` | Defines `local_only_middleware`; no inbound imports found. |
| `core/api/routes.py` | `DEPRECATE` | Defines static route tuple; no inbound imports found. |
| `core/api/main.py` | `DEPRECATE` | Re-exports `build_runtime`; API facade is not an actual service and has no active HTTP runtime. |
| `core/orchestrator/lifecycle.py` | `DEPRECATE` | Alias-only re-export of statuses from `anubis.types`; no inbound imports found. |
| `core/orchestrator/task_router.py` | `DEPRECATE` | Alias-only `TaskRouter = AgentRegistry`; no inbound imports found. |
| `core/orchestrator/state_manager.py` | `DEPRECATE` | Alias-only re-export from `anubis.state`; imported by package init but no independent behavior. |
| `core/execution/error_handler.py` | `DEPRECATE` | Alias-only re-export from `anubis.execution`; no independent behavior. |
| `core/execution/resource_limits.py` | `DEPRECATE` | Alias-only `ResourceLimits = IsolationProfile`; no independent behavior. |
| `core/execution/sandbox.py` | `DEPRECATE` | Alias-only re-export from `anubis.sandbox`; keep only while compatibility imports need it. |
| `src/anubis/core_life/swarm_body/*` | `DEPRECATE` | Entire directory is alias adapters over `anubis.swarm`, `anubis.agents`, and `anubis.memory`; no inbound imports found. |
| `src/anubis/core_life/brain/cognitive_loop.py` | `DEPRECATE` | Thin wrapper around planner; no inbound imports found. |
| `src/anubis/core_life/brain/attention_engine.py` | `DEPRECATE` | Small standalone focus selector; no inbound imports found. |
| `src/anubis/core_life/metabolism/scheduler.py` | `DEPRECATE` | No inbound imports found; appears to be a placeholder service. |
| `src/anubis/core_life/metabolism/workload_balancer.py` | `DEPRECATE` | No inbound imports found; appears to be a placeholder service. |
| `src/anubis/core_life/metabolism/energy_model.py` | `DEPRECATE` | No inbound imports found; appears to be a placeholder service. |
| `src/anubis/core_life/nervous_system/interrupt_system.py` | `DEPRECATE` | No inbound imports found; small standalone state holder. |
| `src/anubis/core_life/nervous_system/reflex_handler.py` | `DEPRECATE` | No inbound imports found; overlaps with safety monitor kill-switch handling. |
| `src/anubis/core_life/nervous_system/signal_router.py` | `DEPRECATE` | No inbound imports found; thin event-bus wrapper. |
| `src/anubis/core_life/immune_system/*` | `DEPRECATE` | Mostly aliases over `anubis.safety`, `anubis.audit`, and `anubis.sandbox`; no inbound imports found. |
| `src/anubis/life_cycle/daily_cycle.py` | `DEPRECATE` | No inbound imports found; tiny tick counter. |
| `src/anubis/life_cycle/reboot_protocol.py` | `DEPRECATE` | Alias-only boot re-export; no inbound imports found. |
| `src/anubis/life_cycle/sleep_cycle.py` | `DEPRECATE` | No inbound imports found; wrapper around compression engine. |
| `src/anubis/observability/behavior_traces.py` | `DEPRECATE` | Schema overlaps with `core/observability/tracer.py`; no inbound imports found. |
| `src/anubis/observability/system_vitals.py` | `DEPRECATE` | Schema overlaps with `core/observability/metrics.py`; no inbound imports found. |
| `src/anubis/core_life/memory_life/identity_memory.py` | `DEPRECATE` | Constant-only identity file; no inbound imports found. |
| `src/anubis/core_life/memory_life/recall_policy.py` | `DEPRECATE` | Helper is not referenced by runtime or tests. |
| Tracked `__pycache__/*.pyc` files | `REMOVE` | Generated bytecode is tracked and mutates during verification. Remove from git in a dedicated cleanup change. |
| `.ruff_cache/` | `REMOVE` | Tool cache should not be source-controlled or audited as source. |

## Keep Findings

| File or Area | Classification | Rationale |
| --- | --- | --- |
| `bootstrap.py` | `KEEP` | Active top-level entrypoint. |
| `core/bootstrap/bootstrap.py` | `KEEP` | Active CLI bootstrap implementation. |
| `core/bootstrap/ultra_light.py` | `KEEP` | Tested minimal runtime surface. |
| `core/graph/*` | `KEEP` | Active deterministic graph runtime. |
| `core/planner/*` | `KEEP` | Active graph planning engine, pending merge decisions. |
| `core/agents/*` | `KEEP` | Active graph stateless agents, pending contract merge decisions. |
| `core/execution/sandbox_runner.py` | `KEEP` | Active graph execution boundary. |
| `core/security/*` | `KEEP` | Strongest canonical candidate for security kernel. |
| `core/memory/*` | `KEEP` | Active graph memory/RAG implementation, pending merge decisions. |
| `core/plugins/*` | `KEEP` | Tested controlled plugin ecosystem, pending merge decisions. |
| `core/swarm/*` | `KEEP` | Tested production-style swarm coordinator. |
| `src/anubis/life_cycle/boot_sequence.py` | `KEEP` | Builds living runtime used by tests and `core/orchestrator`. |
| `src/anubis/core_life/living_loop.py` | `KEEP` | Tested living-loop orchestration path. |
| `src/anubis/memory.py` | `KEEP` | Rich memory policy implementation used by living memory and retrieval. |
| `src/anubis/retrieval.py` | `KEEP` | Tested scoped/global retrieval implementation. |
| `src/anubis/sandbox.py` | `KEEP` | Tested living runtime sandbox. |
| `src/anubis/safety.py` | `KEEP` | Tested anomaly and kill-switch monitor. |
| `src/anubis/audit.py` | `KEEP` | Tested self-audit and tamper detection. |
| `agents/*` | `KEEP` | Used by research hive runtime and tests. |
| `tests/*` | `KEEP` | Broad test coverage; do not remove due to apparent runtime non-use. |
| `tools/*` | `KEEP` | Used by CI and validation commands. |

## Recommended Decommission Plan

1. Declare `core.graph` plus `core.bootstrap` as the canonical active runtime, or explicitly promote the living loop instead.
2. Mark alias-only modules as compatibility surfaces with a deprecation note.
3. Remove tracked generated artifacts first: `__pycache__/*.pyc` and `.ruff_cache/`.
4. Merge duplicate contracts in this order: agent descriptors, memory/retrieval, sandbox/security, execution policy, plugin manifests.
5. Rename top-level `agents/` to a research-specific package or document it as the research-hive agent package.
6. Remove lifecycle and swarm-body stubs only after import-path compatibility is no longer needed.

## Final Assessment

The repository does not have much accidental duplicate text or prompt duplication. Its duplication is systemic: multiple generations of the same architecture are present simultaneously. The safest cleanup path is to keep active and tested systems intact, deprecate alias/stub surfaces, and merge shared contracts before deleting substantial implementation code.
