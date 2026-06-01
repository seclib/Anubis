from __future__ import annotations

from uuid import uuid4

from anubis_ai_core.agent.state_manager import AgentStateManager
from anubis_ai_core.agent.step_executor import AgentStepExecutor
from anubis_ai_core.agent.step_generator import AgentStepGenerationError, AgentStepGenerator
from anubis_ai_core.agent.tool_dispatcher import ToolDispatcher
from anubis_ai_core.memory.interface import AgentMemoryInterface
from anubis_ai_core.models.agent import AgentRunRequest, AgentRunResponse, AgentStep, AgentToolResult, AgentTraceEvent
from anubis_ai_core.observability.agent_trace import AgentTraceLogger, StepTimer


class AgentLoopEngine:
    def __init__(
        self,
        *,
        state_manager: AgentStateManager,
        step_generator: AgentStepGenerator,
        dispatcher: ToolDispatcher,
        memory: AgentMemoryInterface,
        trace_logger: AgentTraceLogger,
    ) -> None:
        self._state_manager = state_manager
        self._step_generator = step_generator
        self._memory = memory
        self._executor = AgentStepExecutor(dispatcher=dispatcher, memory=memory)
        self._trace_logger = trace_logger

    async def run(self, payload: AgentRunRequest, request_id: str) -> AgentRunResponse:
        state = await self._state_manager.get_or_create(payload.conversation_id, payload.input)
        steps: list[AgentStep] = []
        trace: list[AgentTraceEvent] = []
        final_output = ""

        if payload.retrieve_initial_memory and not state.memory_context:
            try:
                memories = await self._memory.retrieve(payload.input, request_id=request_id, limit=5)
                state.memory_context.extend(memories)
                state.tool_results.append(
                    AgentToolResult(
                        tool_name="memory_retrieve",
                        status="succeeded",
                        output={"memories": [memory.model_dump(mode="json") for memory in memories]},
                    )
                )
            except Exception as exc:  # noqa: BLE001 - initial observation degrades safely.
                state.tool_results.append(AgentToolResult(tool_name="memory_retrieve", status="failed", error=str(exc)))

        while not state.termination_flag and state.step_counter < payload.max_steps:
            timer = StepTimer()
            step_id = str(uuid4())
            errors: list[str] = []
            decision: AgentStep | None = None
            input_state = self._trace_logger.snapshot_state(state)
            tool_count_before = len(state.tool_results)

            try:
                decision = await self._step_generator.generate(state)
                steps.append(decision)
                state = await self._executor.execute(state, decision, request_id=request_id)
                if decision.action_type == "respond" and decision.final_output:
                    final_output = decision.final_output
            except AgentStepGenerationError as exc:
                errors.append(str(exc))
                final_output = "I could not produce a valid structured agent step after retries."
                state.termination_flag = True
            except Exception as exc:  # noqa: BLE001 - loop must terminate safely with trace.
                errors.append(str(exc))
                final_output = "The agent loop terminated safely after an execution error."
                state.termination_flag = True

            event = AgentTraceEvent(
                step_id=step_id,
                conversation_id=state.conversation_id,
                step_number=state.step_counter,
                input_state=input_state,
                decision_json=decision.model_dump(mode="json") if decision else None,
                tool_outputs=[
                    result.model_dump(mode="json") for result in state.tool_results[tool_count_before:]
                ],
                timing_ms=timer.elapsed_ms,
                errors=errors,
            )
            trace.append(event)
            self._trace_logger.emit(event)

            if decision and decision.action_type == "respond":
                break
            if decision and decision.final_output and decision.confidence_score > 0.9:
                final_output = decision.final_output
                state.termination_flag = True
                break

        if not final_output:
            final_output = "The agent reached its step limit without a final response."
            state.termination_flag = True

        await self._state_manager.save(state)
        return AgentRunResponse(
            conversation_id=state.conversation_id,
            final_output=final_output,
            state=state,
            steps=steps,
            trace=trace,
            request_id=request_id,
        )
