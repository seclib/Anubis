from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cli.core.context import CliContext
from cli.utils.parser import ParsedCommand


@dataclass(frozen=True)
class CommandResult:
    task: str
    status: dict[str, str] | str
    result: str
    should_continue: bool = True

    def render(self) -> str:
        return "\n".join(
            [
                "TASK:",
                _clean(self.task),
                "",
                "STATUS:",
                _render_status(self.status),
                "",
                "RESULT:",
                _clean(self.result),
                "",
            ]
        )


CommandHandler = Callable[[ParsedCommand, CliContext], CommandResult]


class CommandDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        normalized = name.strip().lower()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        self._handlers[normalized] = handler

    def dispatch(self, command: ParsedCommand, ctx: CliContext) -> CommandResult | None:
        if not command.name:
            return None
        handler = self._handlers.get(command.name)
        if handler is None:
            return CommandResult("Parse command", "error", f"unknown command: {command.name}\nrun: /help")
        result = handler(command, ctx)
        ctx.should_continue = result.should_continue
        return result

    @property
    def commands(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


def _render_status(status: dict[str, str] | str) -> str:
    if isinstance(status, str):
        return _clean(status)
    if not status:
        return "ready"
    if "__logs__" in status:
        return _clean(status["__logs__"])
    return "\n".join(f"- {key}: {value}" for key, value in status.items())


def _clean(value: object) -> str:
    text = str(value).strip()
    return text or "none"
