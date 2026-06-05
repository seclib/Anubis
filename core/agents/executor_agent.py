"""Executor agent: prepares safe sandbox requests without executing them."""

from __future__ import annotations

from core.agents.base_agent import AgentDescriptor, AgentInputError, BaseAgent, StructuredDict


class ExecutorAgent(BaseAgent):
    """Single-responsibility agent for sandbox request construction."""

    def __init__(self) -> None:
        super().__init__(
            descriptor=AgentDescriptor(
                name="executor_agent",
                role="executor",
                capabilities=frozenset({"execution.prepare_sandbox_request"}),
                description="Builds sandbox-only execution requests; never executes directly.",
            )
        )

    def handle(self, input_data: StructuredDict) -> StructuredDict:
        task = self.optional_mapping(input_data, "task")
        if not task:
            raise AgentInputError("missing required dictionary field: task")

        task_id = str(task.get("task_id") or "").strip()
        task_kind = str(task.get("kind") or "").strip()
        objective = str(task.get("objective") or "").strip()
        if not task_id:
            raise AgentInputError("task.task_id is required")
        if not task_kind:
            raise AgentInputError("task.kind is required")
        if not objective:
            raise AgentInputError("task.objective is required")

        capabilities = task.get("required_capabilities", [])
        if not isinstance(capabilities, list):
            raise AgentInputError("task.required_capabilities must be a list")

        return {
            "task_id": task_id,
            "decision": "sandbox_required",
            "sandbox_request": {
                "operation": "agent_task",
                "task_kind": task_kind,
                "objective": objective,
                "required_capabilities": sorted(str(item) for item in capabilities),
                "network": "disabled",
                "filesystem": "sandbox_only",
                "requires_human_approval": False,
            },
            "explanation": (
                "ExecutorAgent only prepares a sandbox request and performs no unsafe operation."
            ),
        }


__all__ = ["ExecutorAgent"]
