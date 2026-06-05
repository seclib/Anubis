"""Runtime assembly layer for Anubis.

Runtime modules wire concrete tools, memory stores, LLM clients, and agent
dependencies. Exports are loaded lazily so importing focused runtime submodules
does not pull in the full orchestration stack during migration.
"""

_EXPORTS = {
    "AgentExecutor": ("runtime.orchestration_engine", "AgentExecutor"),
    "AnubisOrchestrationEngine": ("runtime.orchestration_engine", "AnubisOrchestrationEngine"),
    "ContextToolAdapter": ("runtime.orchestration_engine", "ContextToolAdapter"),
    "DefaultAgentExecutor": ("runtime.orchestration_engine", "DefaultAgentExecutor"),
    "OrchestrationEvent": ("runtime.orchestration_engine", "OrchestrationEvent"),
    "OrchestrationResult": ("runtime.orchestration_engine", "OrchestrationResult"),
    "event_to_dict": ("runtime.orchestration_engine", "event_to_dict"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = __import__(module_name, fromlist=[attribute])
    value = getattr(module, attribute)
    globals()[name] = value
    return value

__all__ = [
    "AgentExecutor",
    "AnubisOrchestrationEngine",
    "ContextToolAdapter",
    "DefaultAgentExecutor",
    "OrchestrationEvent",
    "OrchestrationResult",
    "event_to_dict",
]
