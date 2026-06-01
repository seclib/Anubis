from __future__ import annotations

import json
from typing import Any

from anubis_ai_core.agent.tool_dispatcher import ToolDispatcher
from anubis_ai_core.clients.llm import LlmClient
from anubis_ai_core.models.agent import ToolCall
from anubis_ai_core.models.orchestration import ExecutorOutput, ExecutorStepTrace, PlannerOutput
from anubis_ai_core.orchestrator.json_agent import JsonAgent


class ExecutorAgent(JsonAgent[ExecutorOutput]):
    marker = "ANUBIS_EXECUTOR_JSON"
    model = ExecutorOutput

    def __init__(self, llm_client: LlmClient, dispatcher: ToolDispatcher) -> None:
        super().__init__(llm_client)
        self._dispatcher = dispatcher

    async def execute(
        self,
        *,
        user_input: str,
        plan: PlannerOutput,
        fix_instructions: list[str] | None = None,
    ) -> ExecutorOutput:
        executed_steps: list[ExecutorStepTrace] = []
        missing_info: list[str] = []
        execution_errors: list[str] = []

        subtask_by_id = {subtask.id: subtask for subtask in plan.subtasks}
        for step_id in plan.execution_order:
            subtask = subtask_by_id[step_id]
            if not subtask.tool_needed:
                executed_steps.append(
                    ExecutorStepTrace(
                        step_id=subtask.id,
                        tool_used=None,
                        input={"task": subtask.task},
                        output={"note": "No tool required; task carried into draft synthesis."},
                        status="success",
                    )
                )
                continue

            if subtask.tool_name is None:
                execution_errors.append(f"Subtask {subtask.id} requires a tool but no tool_name was supplied")
                executed_steps.append(
                    ExecutorStepTrace(step_id=subtask.id, input={"task": subtask.task}, status="failed")
                )
                continue

            tool_call = self._tool_call_from_subtask(user_input=user_input, task=subtask.task, tool_name=subtask.tool_name)
            result = await self._dispatcher.dispatch(tool_call)
            status = "success" if result.status == "succeeded" else "failed"
            if result.error:
                execution_errors.append(f"Subtask {subtask.id}: {result.error}")
            executed_steps.append(
                ExecutorStepTrace(
                    step_id=subtask.id,
                    tool_used=subtask.tool_name,
                    input=tool_call.parameters,
                    output=result.output if result.status == "succeeded" else {"error": result.error},
                    status=status,
                )
            )

        prompt = (
            f"{self.marker}\n"
            "You are the Executor Agent. You cannot re-plan. You can only synthesize the provided executed steps.\n"
            "Return STRICT JSON only. No prose. No hidden reasoning.\n"
            "JSON contract:\n"
            "{"
            "\"executed_steps\":[{\"step_id\":1,\"tool_used\":null,\"input\":{},\"output\":{},\"status\":\"success\"}],"
            "\"draft_response\":\"...\","
            "\"missing_info\":[],"
            "\"execution_errors\":[]"
            "}\n"
            f"INPUT_JSON:\n{json.dumps({'user_input': user_input, 'plan': plan.model_dump(mode='json'), 'executed_steps': [step.model_dump(mode='json') for step in executed_steps], 'fix_instructions': fix_instructions or [], 'execution_errors': execution_errors, 'missing_info': missing_info}, ensure_ascii=True)}"
        )
        output = await self.complete_json(prompt)
        return output.model_copy(
            update={
                "executed_steps": executed_steps,
                "execution_errors": execution_errors + output.execution_errors,
                "missing_info": missing_info + output.missing_info,
            }
        )

    def _tool_call_from_subtask(self, *, user_input: str, task: str, tool_name: str) -> ToolCall:
        parameters: dict[str, Any]
        if tool_name in {"rag_query", "memory_retrieve"}:
            parameters = {"query": user_input, "limit": 5}
        elif tool_name == "web_search":
            parameters = {"query": user_input, "limit": 5}
        elif tool_name == "file_read":
            parameters = {"relative_path": self._extract_relative_path(user_input), "max_bytes": 12000}
        elif tool_name == "file_write":
            parameters = {"title": "Anubis Generated Note", "content": task}
        else:
            parameters = {}
        return ToolCall(tool_name=tool_name, parameters=parameters, input_schema={"type": "object"}, async_flag=False)

    def _extract_relative_path(self, user_input: str) -> str:
        tokens = [token.strip("'\"`") for token in user_input.split()]
        for token in tokens:
            if "/" in token or "." in token:
                return token
        return "README.md"
