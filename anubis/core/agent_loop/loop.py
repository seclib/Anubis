from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from anubis.core.agent_loop.context import ContextProvider, TaskContextProvider
from anubis.core.executor.executor import PlanExecution, ToolDrivenExecutor
from anubis.core.planner.planner import DefaultPlanner
from anubis.core.states import AgentExecutionState
from anubis.core.verifier.verifier import DefaultVerifier
from anubis.types import AgentContext, HistoryEvent, Plan, StepExecution, TaskSnapshot, Verification


class ProductionAgentLoop:
    def __init__(
        self,
        planner: DefaultPlanner | None = None,
        executor: ToolDrivenExecutor | None = None,
        verifier: DefaultVerifier | None = None,
        context_provider: ContextProvider | None = None,
        max_retries: int = 2,
    ) -> None:
        self.planner = planner or DefaultPlanner()
        self.executor = executor or ToolDrivenExecutor()
        self.verifier = verifier or DefaultVerifier()
        self.context_provider = context_provider or TaskContextProvider()
        self.max_retries = max(0, max_retries)

    def run(self, task: TaskSnapshot) -> TaskSnapshot:
        current = _copy_task(task)
        current["status"] = "running"
        feedback = ""

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                self._record_state(current, AgentExecutionState.RETRYING, {"attempt": attempt, "feedback": feedback})
                current["context"] = {**current.get("context", {}), "retry_feedback": feedback}

            self._record_state(current, AgentExecutionState.PLANNING, {"attempt": attempt})
            context = self.get_context(current)
            plan = self.plan(current, context)
            current["plan"] = _plan_payload(plan)

            self._record_state(current, AgentExecutionState.EXECUTING, {"steps": len(plan.steps)})
            execution = self._execute_plan(plan)

            self._record_state(current, AgentExecutionState.VERIFYING, {"steps": len(execution.steps)})
            verification = self._verify_plan(current, execution)
            self._record_history(
                current,
                "agent_iteration",
                {
                    "attempt": attempt,
                    "context": _context_payload(context),
                    "plan": _plan_payload(plan),
                    "execution": _execution_payload(execution),
                    "verification": _verification_payload(verification),
                },
            )

            if verification.success:
                current["status"] = "done"
                return current
            if not verification.retry:
                current["status"] = "failed"
                return current
            feedback = verification.reason

        current["status"] = "failed"
        return current

    def step(self, task: TaskSnapshot) -> StepExecution:
        context = self.get_context(task)
        plan = self.plan(task, context)
        if not plan.steps:
            empty_result = {
                "tool": "",
                "input": {},
                "output": {"type": "NoExecutableStep"},
                "success": False,
                "error": "planner produced no executable tool steps",
                "logs": [],
                "duration_ms": 0,
            }
            from anubis.types import PlanStep

            return StepExecution(PlanStep(0, "No executable step"), empty_result, False)
        return self.executor.execute_step(plan.steps[0])

    def plan(self, task: TaskSnapshot, context: AgentContext) -> Plan:
        return self.planner.plan(task, context)

    def verify(self, task: TaskSnapshot, execution: StepExecution) -> Verification:
        return self.verifier.validate_task_success(task, execution)

    def get_context(self, task: TaskSnapshot) -> AgentContext:
        return self.context_provider.get_context(task)

    def _execute_plan(self, plan: Plan) -> PlanExecution:
        return self.executor.execute_plan(plan)

    def _verify_plan(self, task: TaskSnapshot, execution: PlanExecution) -> Verification:
        return self.verifier.verify_plan(task, execution)

    def _record_state(self, task: TaskSnapshot, state: AgentExecutionState, payload: dict[str, Any]) -> None:
        self._record_history(task, "state_changed", {"state": state.value, **payload})

    def _record_history(self, task: TaskSnapshot, event: str, payload: dict[str, Any]) -> None:
        task.setdefault("history", []).append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                "payload": payload,
            }
        )


def _copy_task(task: TaskSnapshot) -> TaskSnapshot:
    return {
        "id": task["id"],
        "goal": task["goal"],
        "status": task["status"],
        "context": dict(task.get("context", {})),
        "plan": dict(task.get("plan", {})),
        "history": list(task.get("history", [])),
    }


def _context_payload(context: AgentContext) -> dict[str, Any]:
    return {
        "task_id": context.task_id,
        "goal": context.goal,
        "compressed": context.compressed,
        "chunks": [asdict(chunk) for chunk in context.chunks],
        "metadata": context.metadata,
    }


def _plan_payload(plan: Plan) -> dict[str, Any]:
    return {
        "task_id": plan.task_id,
        "goal": plan.goal,
        "steps": [asdict(step) for step in plan.steps],
        "metadata": plan.metadata,
    }


def _execution_payload(execution: PlanExecution) -> dict[str, Any]:
    return {
        "success": execution.success,
        "steps": [asdict(step) for step in execution.steps],
    }


def _verification_payload(verification: Verification) -> dict[str, Any]:
    return asdict(verification)


__all__ = ["ProductionAgentLoop"]
