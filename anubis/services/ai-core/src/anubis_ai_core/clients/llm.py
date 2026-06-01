from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod

from anubis_ai_core.models.llm import LlmResponse


class LlmClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> LlmResponse:
        raise NotImplementedError


class MockLlmClient(LlmClient):
    async def complete(self, prompt: str) -> LlmResponse:
        await asyncio.sleep(0)
        if "ANUBIS_AGENT_STEP_JSON" in prompt:
            return LlmResponse(content=self._agent_step_response(prompt))
        if "ANUBIS_PLANNER_JSON" in prompt:
            return LlmResponse(content=self._planner_response(prompt))
        if "ANUBIS_EXECUTOR_JSON" in prompt:
            return LlmResponse(content=self._executor_response(prompt))
        if "ANUBIS_CRITIC_JSON" in prompt:
            return LlmResponse(content=self._critic_response(prompt))
        return LlmResponse(
            content=(
                "I am running in local mock mode. I received your request and retrieved any available "
                "workspace context. Configure a provider-backed LLM client for production inference."
            )
        )

    def _agent_step_response(self, prompt: str) -> str:
        state = self._extract_state(prompt)
        step_counter = int(state.get("step_counter", 0))
        messages = state.get("messages", [])
        memory_context = state.get("memory_context", [])
        tool_results = state.get("tool_results", [])
        latest_user = next((message.get("content", "") for message in reversed(messages) if message.get("role") == "user"), "")
        lowered = latest_user.lower()

        if step_counter == 0 and any(token in lowered for token in ("remember", "previous", "prior", "memory", "decide", "decision")):
            return json.dumps(
                {
                    "observation": "The user request appears to require durable context.",
                    "reasoning_summary": "Retrieve memory before answering.",
                    "action_type": "retrieve_memory",
                    "tool_call": {
                        "tool_name": "memory_retrieve",
                        "input_schema": {"type": "object"},
                        "parameters": {"query": latest_user, "limit": 5},
                        "async_flag": False,
                    },
                    "final_output": None,
                    "confidence_score": 0.72,
                }
            )
        if step_counter == 0 and any(token in lowered for token in ("store", "save this", "remember that", "preference")):
            return json.dumps(
                {
                    "observation": "The user provided content that may be useful long term.",
                    "reasoning_summary": "Store only the explicit durable statement.",
                    "action_type": "store_memory",
                    "tool_call": {
                        "tool_name": "memory_store",
                        "input_schema": {"type": "object"},
                        "parameters": {
                            "namespace": "agent",
                            "content": latest_user,
                            "metadata": {"source": "agent_loop"},
                        },
                        "async_flag": False,
                    },
                    "final_output": None,
                    "confidence_score": 0.81,
                }
            )
        if step_counter == 0 and any(token in lowered for token in ("file", "read")):
            return json.dumps(
                {
                    "observation": "The user request may require file access through a controlled tool.",
                    "reasoning_summary": "Ask for a safe file_read only if a relative_path is supplied.",
                    "action_type": "respond",
                    "tool_call": None,
                    "final_output": "Please provide a workspace-relative path for file inspection.",
                    "confidence_score": 0.92,
                }
            )
        context_count = len(memory_context)
        tool_count = len(tool_results)
        return json.dumps(
            {
                "observation": "The agent has enough context to produce a bounded response.",
                "reasoning_summary": "Respond using current conversation, retrieved memory, and tool results.",
                "action_type": "respond",
                "tool_call": None,
                "final_output": (
                    "Agent loop completed. "
                    f"Observed {context_count} memory item(s) and {tool_count} tool result(s). "
                    "This local mock response follows the structured agent contract."
                ),
                "confidence_score": 0.94,
            }
        )

    def _extract_state(self, prompt: str) -> dict:
        marker = "STATE_JSON:\n"
        if marker not in prompt:
            return {}
        raw = prompt.split(marker, 1)[1].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _planner_response(self, prompt: str) -> str:
        data = self._extract_input(prompt)
        user_input = str(data.get("user_input", ""))
        lowered = user_input.lower()
        subtasks = []
        if any(token in lowered for token in ("memory", "remember", "previous", "prior", "decision", "decide")):
            subtasks.append(
                {
                    "id": 1,
                    "task": "Retrieve relevant memory before drafting an answer.",
                    "tool_needed": True,
                    "tool_name": "memory_retrieve",
                    "dependencies": [],
                }
            )
            subtasks.append(
                {
                    "id": 2,
                    "task": "Synthesize a grounded response from retrieved memory and user input.",
                    "tool_needed": False,
                    "tool_name": None,
                    "dependencies": [1],
                }
            )
        elif any(token in lowered for token in ("search", "web", "latest")):
            subtasks.append(
                {
                    "id": 1,
                    "task": "Search for relevant external context using the controlled search tool.",
                    "tool_needed": True,
                    "tool_name": "web_search",
                    "dependencies": [],
                }
            )
            subtasks.append(
                {
                    "id": 2,
                    "task": "Draft a response using only structured tool output.",
                    "tool_needed": False,
                    "tool_name": None,
                    "dependencies": [1],
                }
            )
        elif any(token in lowered for token in ("file", "read")):
            subtasks.append(
                {
                    "id": 1,
                    "task": "Read the requested workspace-relative file through the file tool.",
                    "tool_needed": True,
                    "tool_name": "file_read",
                    "dependencies": [],
                }
            )
        else:
            subtasks.append(
                {
                    "id": 1,
                    "task": "Draft a direct response from the user input.",
                    "tool_needed": False,
                    "tool_name": None,
                    "dependencies": [],
                }
            )
        return json.dumps(
            {
                "goal": user_input or "Handle user request",
                "subtasks": subtasks,
                "execution_order": [subtask["id"] for subtask in subtasks],
                "risk_notes": "Mock planner: verify tool outputs before relying on them.",
                "confidence": 0.82,
            }
        )

    def _executor_response(self, prompt: str) -> str:
        data = self._extract_input(prompt)
        executed_steps = data.get("executed_steps", [])
        errors = data.get("execution_errors", [])
        user_input = str(data.get("user_input", ""))
        successful_tools = [
            step.get("tool_used")
            for step in executed_steps
            if step.get("tool_used") and step.get("status") == "success"
        ]
        draft = (
            "Executor draft: completed the planned pipeline. "
            f"User request: {user_input}. "
            f"Successful tools: {', '.join(successful_tools) if successful_tools else 'none'}."
        )
        if errors:
            draft += f" Recoverable execution errors: {'; '.join(map(str, errors))}."
        return json.dumps(
            {
                "executed_steps": executed_steps,
                "draft_response": draft,
                "missing_info": [],
                "execution_errors": errors,
            }
        )

    def _critic_response(self, prompt: str) -> str:
        data = self._extract_input(prompt)
        executor_output = data.get("executor_output", {})
        errors = executor_output.get("execution_errors", [])
        draft = str(executor_output.get("draft_response", ""))
        if errors or not draft:
            return json.dumps(
                {
                    "score": 0.46,
                    "approved": False,
                    "issues": [
                        {
                            "type": "error",
                            "description": "Executor output contains errors or an empty draft.",
                            "severity": "medium",
                        }
                    ],
                    "fix_instructions": ["Regenerate the executor draft with available structured results only."],
                    "final_response": None,
                }
            )
        return json.dumps(
            {
                "score": 0.91,
                "approved": True,
                "issues": [],
                "fix_instructions": [],
                "final_response": draft,
            }
        )

    def _extract_input(self, prompt: str) -> dict:
        marker = "INPUT_JSON:\n"
        if marker not in prompt:
            return {}
        raw = prompt.split(marker, 1)[1].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
