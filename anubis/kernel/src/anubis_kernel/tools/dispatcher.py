from __future__ import annotations

from anubis_kernel.agent.schemas import ToolCall
from anubis_kernel.sandbox.executor import FunctionSandbox
from anubis_kernel.tools.schemas import RegisteredTool
from anubis_kernel.tools.validator import ToolValidationError, validate_parameters


class ToolDispatcher:
    def __init__(self, *, registry: dict[str, RegisteredTool], sandbox: FunctionSandbox) -> None:
        self._registry = registry
        self._sandbox = sandbox

    async def dispatch(self, call: ToolCall) -> dict:
        tool = self._registry.get(call.tool_name)
        if tool is None:
            return {"status": "failed", "error": "UNKNOWN_TOOL", "summary": "unknown tool"}
        try:
            validate_parameters(tool.definition.parameters_schema, call.parameters)
            output = await self._sandbox.execute(
                tool_name=call.tool_name,
                parameters=call.parameters,
                executor=tool.executor,
                timeout_seconds=tool.definition.timeout_seconds,
            )
            return {"status": "succeeded", **output}
        except ToolValidationError as exc:
            return {"status": "failed", "error": "INVALID_TOOL_INPUT", "summary": str(exc)}
        except TimeoutError:
            return {"status": "failed", "error": "TOOL_TIMEOUT", "summary": "tool timed out"}
        except Exception:
            return {"status": "failed", "error": "TOOL_FAILED", "summary": "tool failed safely"}
