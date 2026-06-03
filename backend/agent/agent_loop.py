from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.context import ContextEngine
from backend.agent.executor import ExecutionResult, Executor
from backend.agent.executor import ToolInvoker
from backend.agent.planner import AgentContext, Planner
from backend.agent.task_manager import TaskManager
from backend.agent.verifier import VerificationResult, Verifier
from backend.tools import invoke_tool


@dataclass(frozen=True)
class AgentRound:
    iteration: int
    context: AgentContext
    plan: dict[str, Any]
    execution: dict[str, Any]
    verification: VerificationResult


@dataclass(frozen=True)
class AgentLoopResult:
    task_id: str
    task: str
    done: bool
    rounds: list[AgentRound] = field(default_factory=list)
    final_reason: str = ""


class AgentLoop:
    def __init__(
        self,
        planner: Planner | None = None,
        executor: Executor | None = None,
        verifier: Verifier | None = None,
        context_engine: ContextEngine | None = None,
        task_manager: TaskManager | None = None,
        context_tool_invoker: ToolInvoker = invoke_tool,
        max_iterations: int = 3,
    ) -> None:
        self.planner = planner or Planner()
        self.executor = executor or Executor()
        self.verifier = verifier or Verifier()
        self.context_engine = context_engine or ContextEngine()
        self.task_manager = task_manager or TaskManager()
        self.context_tool_invoker = context_tool_invoker
        self.max_iterations = max_iterations

    def run(self, task: str) -> AgentLoopResult:
        tracked_task = self.task_manager.create_task(task)
        self.task_manager.start_task(tracked_task.id)
        rounds: list[AgentRound] = []
        feedback = ""

        for iteration in range(1, self.max_iterations + 1):
            context = self.get_context(task, feedback)
            self.task_manager.update_context(tracked_task.id, asdict(context))
            plan = self.planner.plan(task, context)
            plan_dict = _plan_to_dict(plan)
            self.task_manager.update_plan(tracked_task.id, plan_dict)
            execution = self.executor.execute(plan)
            execution_dict = _execution_to_dict(execution)
            verification = self.verifier.verify(execution)
            self.task_manager.log_action(
                tracked_task.id,
                "agent_round",
                {
                    "iteration": iteration,
                    "execution": execution_dict,
                    "verification": asdict(verification),
                },
            )
            rounds.append(
                AgentRound(
                    iteration=iteration,
                    context=context,
                    plan=plan_dict,
                    execution=execution_dict,
                    verification=verification,
                )
            )

            if verification.done:
                self.task_manager.complete_task(tracked_task.id, verification.reason)
                return AgentLoopResult(
                    task_id=tracked_task.id,
                    task=task,
                    done=True,
                    rounds=rounds,
                    final_reason=verification.reason,
                )
            if not verification.retry:
                self.task_manager.fail_task(tracked_task.id, verification.reason)
                return AgentLoopResult(
                    task_id=tracked_task.id,
                    task=task,
                    done=False,
                    rounds=rounds,
                    final_reason=verification.reason,
                )
            feedback = verification.reason

        self.task_manager.fail_task(tracked_task.id, "max iterations reached")
        return AgentLoopResult(
            task_id=tracked_task.id,
            task=task,
            done=False,
            rounds=rounds,
            final_reason="max iterations reached",
        )

    def get_context(self, task: str, retry_feedback: str = "") -> AgentContext:
        query = f"{task}\n{retry_feedback}".strip() if retry_feedback else task
        repo_context = self.context_engine.context_for_task(query)
        items = [
            {
                "source": "context_engine",
                "success": True,
                "output": {
                    "chunks": repo_context.chunks,
                    "text": repo_context.text,
                    "token_budget_chars": repo_context.token_budget_chars,
                },
            },
            self.context_tool_invoker("git_diff", {}),
        ]
        return AgentContext(
            task=task,
            items=items,
            compressed=repo_context.text,
            retry_feedback=retry_feedback,
        )


def run_agent_loop(task: str, max_iterations: int = 3) -> dict[str, Any]:
    return asdict(AgentLoop(max_iterations=max_iterations).run(task))


def _plan_to_dict(plan: Any) -> dict[str, Any]:
    return asdict(plan)


def _execution_to_dict(execution: ExecutionResult) -> dict[str, Any]:
    return asdict(execution)


__all__ = ["AgentLoop", "AgentLoopResult", "AgentRound", "run_agent_loop"]
