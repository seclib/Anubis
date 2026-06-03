# Simplified Agent Architecture

ANUBIS production execution should converge on three distributed agent roles:

## Planner

Responsible for:

- Goal decomposition
- DAG planning
- Dependency definition
- Parallel execution opportunities
- Structured success criteria

Forbidden:

- Tool execution
- File writes
- Review approval

## Executor

Responsible for:

- Executing assigned DAG nodes
- Calling sandboxed tools
- Running tests and commands
- Returning structured step results

Forbidden:

- Planning next steps
- Self-approval
- Direct host access

## Reviewer

Responsible for:

- Validating executor results
- Interpreting test output
- Detecting broken states
- Risk scoring
- Approve, retry, or rollback recommendations

Forbidden:

- Implementing changes
- Executing tools
- Creating plans

## What Is No Longer An Agent

These capabilities remain in ANUBIS, but as platform services:

- Orchestration: `DistributedOrchestrator`
- Memory: `UnifiedMemoryService`
- Security/SOC: security layer and SOC services
- Git: git service / executor-backed git operations
- CI/CD: pipeline service

## Legacy Consolidation Map

| Legacy component | Target | Action |
| --- | --- | --- |
| `orchestrator_agent` | orchestration service | replace |
| `coder_agent` | Executor | merge |
| `tester_agent` | Executor + Reviewer | split execution from interpretation |
| `debugger_agent` | Reviewer | merge failure analysis |
| `memory_agent` | memory service | replace |
| `critic_agent` | Reviewer | merge policy checks |
| `meta_cognition_agent` | Reviewer/security | merge behavioral drift checks |
| `loop_optimizer` | orchestration service | replace |

## Migration Plan

1. Freeze new feature work on legacy reasoning agents in `agent/` and `backend/agent/`.
2. Route new distributed work only through `AgentType.PLANNER`, `AgentType.EXECUTOR`, and `AgentType.REVIEWER`.
3. Replace legacy `orchestrator_agent` call sites with `DistributedOrchestrator`.
4. Move `coder_agent` behavior into executor step handlers.
5. Move test command execution into Executor; move test interpretation into Reviewer.
6. Move `debugger_agent`, `critic_agent`, and `meta_cognition_agent` logic into Reviewer validation policies.
7. Move `memory_agent` behavior into `UnifiedMemoryService`.
8. Run parity tests for planning, execution, review, memory recall, and rollback signaling.
9. Mark legacy modules deprecated once no production runtime path imports them.
10. Delete legacy modules only after tests and runtime import scans show zero dependency.

## Canonical Code Contract

The machine-readable source of truth is:

- `anubis.distributed.contracts.AgentType`
- `anubis.distributed.agent_architecture.simplified_agent_architecture`
