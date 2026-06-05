from __future__ import annotations

from anubis_cli_loader import load_unified_module


_agent = load_unified_module("core/agent.py", "anubis_cli_unified_agent")

AgentPlan = _agent.AgentPlan
AgentStep = _agent.AgentStep
AnubisAgent = _agent.AnubisAgent
AnubisCLI = _agent.AnubisCLI
Critique = _agent.Critique
StepResult = _agent.StepResult
StreamingOllama = _agent.StreamingOllama
Terminal = _agent.Terminal
async_main = _agent.async_main
build_parser = _agent.build_parser
main = _agent.main

__all__ = [
    "AgentPlan",
    "AgentStep",
    "AnubisAgent",
    "AnubisCLI",
    "Critique",
    "StepResult",
    "StreamingOllama",
    "Terminal",
    "async_main",
    "build_parser",
    "main",
]
