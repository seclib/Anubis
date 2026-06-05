# ANUBIS Architecture Scaffold

ANUBIS is being bootstrapped as a production-grade AI coding agent inspired by Claude Code / Codex.

This directory is the Phase 0 architecture foundation only. It contains structure and placeholder entry files, not feature implementation.

## Layers

- `core/`: agent loop, planner, executor, verifier
- `tools/`: filesystem, shell command, and git system tools
- `context/`: task-driven repository context indexing, retrieval, and compression
- `task/`: task manager boundary
- `models/`: model routing boundary
- `ui/`: desktop UI boundary
- `logs/`: execution trace storage boundary
- `tests/`: architecture and module tests

## Phase 0 Rule

No implementation logic belongs here yet. Later phases should fill these module boundaries while preserving the layer separation defined in `implementation.md`.
