from __future__ import annotations

from collections.abc import Callable

from cli_mvp.commands.agent import agent_command
from cli_mvp.commands.context import CommandContext
from cli_mvp.commands.execution import analyze_command, build_command, research_command
from cli_mvp.commands.memory import memory_command
from cli_mvp.commands.swarm import swarm_command
from cli_mvp.commands.system import exit_command, help_command, status_command
from cli_mvp.models import Command


CommandHandler = Callable[[Command, CommandContext], None]


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self.register_defaults()

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> CommandHandler | None:
        return self._handlers.get(name)

    def register_defaults(self) -> None:
        self.register("/help", help_command)
        self.register("/status", status_command)
        self.register("/exit", exit_command)
        self.register("/quit", exit_command)
        self.register("/build", build_command)
        self.register("/analyze", analyze_command)
        self.register("/research", research_command)
        self.register("/agent", agent_command)
        self.register("/swarm", swarm_command)
        self.register("/memory", memory_command)
