from __future__ import annotations

import shlex
from dataclasses import dataclass

from anubis.core.session import SessionRuntime


@dataclass(frozen=True)
class SessionCommandResult:
    text: str
    should_continue: bool = True


class SessionCommandController:
    """Runtime commands for the Anubis Code terminal surface."""

    def __init__(self, runtime: SessionRuntime) -> None:
        self.runtime = runtime

    def route(self, line: str) -> SessionCommandResult | None:
        parts = _split(line)
        if not parts:
            return None
        command = parts[0].lower()
        args = parts[1:]
        if command == "/tools":
            return SessionCommandResult(self._tools())
        if command == "/memory":
            return SessionCommandResult(self._memory(args))
        if command == "/compact":
            return SessionCommandResult(self._compact())
        if command == "/agents":
            return SessionCommandResult(self._agents())
        if command == "/model":
            return SessionCommandResult(self._model(args))
        if command == "/auto":
            return SessionCommandResult(self._auto(args))
        if command == "/anubis":
            return SessionCommandResult(self._anubis())
        return None

    def _tools(self) -> str:
        lines = ["ANUBIS CODE TOOLS:"]
        for tool in self.runtime.orchestrator.tools.discover():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines) + "\n"

    def _memory(self, args: list[str]) -> str:
        query = " ".join(args).strip()
        if query:
            items = self.runtime.memory.retrieve(query, limit=10)
            lines = [f"MEMORY SEARCH: {query}", *(f"- {item}" for item in items)]
            if len(lines) == 1:
                lines.append("- no matching session memory")
            return "\n".join(lines) + "\n"
        return (
            "MEMORY:\n"
            f"- transcript messages: {len(self.runtime.memory.transcript)}\n"
            f"- facts: {len(self.runtime.memory.facts)}\n"
            f"- tool results: {len(self.runtime.memory.tool_history)}\n"
        )

    def _compact(self) -> str:
        return "COMPACTED CONTEXT:\n" + self.runtime.memory.compact() + "\n"

    def _agents(self) -> str:
        return "\n".join(
            [
                "ANUBIS CODE AGENTS:",
                "- planner: plans short execution paths",
                "- executor: selects tools or final response",
                "- reviewer: verifies result and risk",
            ]
        ) + "\n"

    def _model(self, args: list[str]) -> str:
        router = self.runtime.llm_router
        if args:
            model = args[0]
            router.default_model = model
            router.code_model = model
            router.fast_model = model
            router.review_model = model
        return "\n".join(
            [
                "MODELS:",
                f"- default: {router.default_model}",
                f"- code: {router.code_model}",
                f"- fast: {router.fast_model}",
                f"- review: {router.review_model}",
            ]
        ) + "\n"

    def _auto(self, args: list[str]) -> str:
        if args:
            value = args[0].lower()
            if value in {"on", "true", "1", "yes"}:
                self.runtime.settings.autonomous = True
            elif value in {"off", "false", "0", "no"}:
                self.runtime.settings.autonomous = False
        state = "on" if self.runtime.settings.autonomous else "off"
        return (
            "AUTONOMOUS MODE:\n"
            f"- state: {state}\n"
            f"- max tool calls: {self.runtime.settings.max_tool_calls}\n"
            f"- shell timeout: {self.runtime.settings.shell_timeout}s\n"
        )

    def _anubis(self) -> str:
        return "\n".join(
            [
                "ANUBIS CODE:",
                "- local AI engineer terminal",
                "- Ollama/Qwen model routing",
                "- planner/executor/reviewer agents",
                "- filesystem and shell tools",
                "- session memory and compacted context",
            ]
        ) + "\n"


def _split(line: str) -> list[str]:
    try:
        return shlex.split(line.strip())
    except ValueError:
        return line.strip().split()


__all__ = ["SessionCommandController", "SessionCommandResult"]
