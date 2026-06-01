from __future__ import annotations

from anubis_ai_core.models.orchestration import (
    CriticIssue,
    CriticOutput,
    ExecutorOutput,
    MemoryWriteDecision,
    OrchestratorRunRequest,
    OrchestratorRunResponse,
    OrchestrationTraceEvent,
    PlannerOutput,
)
from anubis_ai_core.orchestrator.critic_agent import CriticAgent
from anubis_ai_core.orchestrator.executor_agent import ExecutorAgent
from anubis_ai_core.orchestrator.memory_write_policy import MemoryWritePolicy
from anubis_ai_core.orchestrator.planner_agent import PlannerAgent
from anubis_ai_core.orchestrator.session_manager import OrchestrationSessionManager
from anubis_ai_core.orchestrator.trace_logger import OrchestrationTraceLogger, StageTimer


class MultiAgentOrchestrator:
    def __init__(
        self,
        *,
        planner: PlannerAgent,
        executor: ExecutorAgent,
        critic: CriticAgent,
        session_manager: OrchestrationSessionManager,
        memory_write_policy: MemoryWritePolicy,
        trace_logger: OrchestrationTraceLogger,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._critic = critic
        self._session_manager = session_manager
        self._memory_write_policy = memory_write_policy
        self._trace_logger = trace_logger

    async def run(self, payload: OrchestratorRunRequest, request_id: str) -> OrchestratorRunResponse:
        trace = list(payload.replay_trace or [])
        timer = StageTimer()
        session = await self._session_manager.start(payload.conversation_id, payload.input)
        conversation_id = session.conversation_id
        trace.append(
            self._trace_logger.event(
                conversation_id=conversation_id,
                loop_iteration=0,
                stage="session_manager",
                payload={"session": session.model_dump(mode="json")},
                latency_ms=timer.elapsed_ms,
            )
        )
        plan: PlannerOutput | None = None
        executor_output: ExecutorOutput | None = None
        critic_output: CriticOutput | None = None
        fix_instructions: list[str] = []

        for iteration in range(1, payload.max_iterations + 1):
            if plan is None or self._requires_replan(fix_instructions):
                timer = StageTimer()
                try:
                    plan = await self._planner.plan(payload.input, memory_hint=None)
                    trace.append(
                        self._trace_logger.event(
                            conversation_id=conversation_id,
                            loop_iteration=iteration,
                            stage="planner",
                            payload={"planner_output": plan.model_dump(mode="json")},
                            latency_ms=timer.elapsed_ms,
                        )
                    )
                except Exception as exc:
                    fallback_plan = self._fallback_plan(payload.input)
                    plan = fallback_plan
                    trace.append(
                        self._trace_logger.event(
                            conversation_id=conversation_id,
                            loop_iteration=iteration,
                            stage="planner",
                            payload={"planner_output": fallback_plan.model_dump(mode="json")},
                            latency_ms=timer.elapsed_ms,
                            errors=[str(exc)],
                        )
                    )

            timer = StageTimer()
            try:
                executor_output = await self._executor.execute(
                    user_input=payload.input,
                    plan=plan,
                    fix_instructions=fix_instructions,
                )
                trace.append(
                    self._trace_logger.event(
                        conversation_id=conversation_id,
                        loop_iteration=iteration,
                        stage="executor",
                        payload={"executor_trace": executor_output.model_dump(mode="json")},
                        latency_ms=timer.elapsed_ms,
                    )
                )
            except Exception as exc:
                executor_output = ExecutorOutput(
                    draft_response="",
                    execution_errors=[f"Executor failed recoverably: {exc}"],
                )
                trace.append(
                    self._trace_logger.event(
                        conversation_id=conversation_id,
                        loop_iteration=iteration,
                        stage="executor",
                        payload={"executor_trace": executor_output.model_dump(mode="json")},
                        latency_ms=timer.elapsed_ms,
                        errors=[str(exc)],
                    )
                )

            timer = StageTimer()
            try:
                critic_output = await self._critic.critique(
                    user_input=payload.input,
                    plan=plan,
                    executor_output=executor_output,
                )
                trace.append(
                    self._trace_logger.event(
                        conversation_id=conversation_id,
                        loop_iteration=iteration,
                        stage="critic",
                        payload={"critic_evaluation": critic_output.model_dump(mode="json")},
                        latency_ms=timer.elapsed_ms,
                    )
                )
            except Exception as exc:
                critic_output = CriticOutput(
                    score=0.0,
                    approved=False,
                    issues=[
                        CriticIssue(
                            type="error",
                            description=f"Critic failed validation: {exc}",
                            severity="high",
                        )
                    ],
                    fix_instructions=["Regenerate executor draft with fewer assumptions and include execution errors."],
                    final_response=None,
                )
                trace.append(
                    self._trace_logger.event(
                        conversation_id=conversation_id,
                        loop_iteration=iteration,
                        stage="critic",
                        payload={"critic_evaluation": critic_output.model_dump(mode="json")},
                        latency_ms=timer.elapsed_ms,
                        errors=[str(exc)],
                    )
                )

            if critic_output.approved:
                final_response = critic_output.final_response or executor_output.draft_response
                memory_write_decision = self._memory_write_policy.decide(
                    user_input=payload.input,
                    final_response=final_response,
                    approved=True,
                )
                trace.extend(
                    self._final_trace_events(
                        conversation_id=conversation_id,
                        iteration=iteration,
                        final_response=final_response,
                        memory_write_decision=memory_write_decision,
                    )
                )
                return OrchestratorRunResponse(
                    conversation_id=conversation_id,
                    final_response=final_response,
                    approved=True,
                    iterations=iteration,
                    session=session,
                    plan=plan,
                    executor_output=executor_output,
                    critic_output=critic_output,
                    memory_write_decision=memory_write_decision,
                    trace=trace,
                    request_id=request_id,
                )
            fix_instructions = critic_output.fix_instructions

        assert plan is not None
        assert executor_output is not None
        assert critic_output is not None
        final_response = executor_output.draft_response or "The multi-agent pipeline did not produce an approved final response."
        memory_write_decision = self._memory_write_policy.decide(
            user_input=payload.input,
            final_response=final_response,
            approved=False,
        )
        trace.extend(
            self._final_trace_events(
                conversation_id=conversation_id,
                iteration=payload.max_iterations,
                final_response=final_response,
                memory_write_decision=memory_write_decision,
            )
        )
        return OrchestratorRunResponse(
            conversation_id=conversation_id,
            final_response=final_response,
            approved=False,
            iterations=payload.max_iterations,
            session=session,
            plan=plan,
            executor_output=executor_output,
            critic_output=critic_output,
            memory_write_decision=memory_write_decision,
            trace=trace,
            request_id=request_id,
        )

    def _requires_replan(self, fix_instructions: list[str]) -> bool:
        joined = " ".join(fix_instructions).lower()
        return "replan" in joined or "plan" in joined and "missing" in joined

    def _fallback_plan(self, user_input: str) -> PlannerOutput:
        return PlannerOutput(
            goal=user_input,
            subtasks=[
                {
                    "id": 1,
                    "task": "Answer using available context without external assumptions.",
                    "tool_needed": False,
                    "tool_name": None,
                    "dependencies": [],
                }
            ],
            execution_order=[1],
            risk_notes="Fallback plan created after planner validation failure.",
            confidence=0.35,
        )

    def _final_trace_events(
        self,
        *,
        conversation_id: str,
        iteration: int,
        final_response: str,
        memory_write_decision: MemoryWriteDecision,
    ) -> list[OrchestrationTraceEvent]:
        final_timer = StageTimer()
        final_event = self._trace_logger.event(
            conversation_id=conversation_id,
            loop_iteration=iteration,
            stage="final_response",
            payload={"final_response": final_response},
            latency_ms=final_timer.elapsed_ms,
        )
        memory_timer = StageTimer()
        memory_event = self._trace_logger.event(
            conversation_id=conversation_id,
            loop_iteration=iteration,
            stage="memory_write_decision",
            payload={"memory_write_decision": memory_write_decision.model_dump(mode="json")},
            latency_ms=memory_timer.elapsed_ms,
        )
        return [final_event, memory_event]
