from __future__ import annotations

import shlex
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from anubis.agents import CORE_AGENTS, AgentRegistry, SwarmEngine
from cli.ux import render_block

DEFAULT_STATE: dict[str, Any] = {
    "agents": dict(CORE_AGENTS)
}


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str] = field(default_factory=list)
    raw_args: str = ""


@dataclass(frozen=True)
class RouteResult:
    task: str
    status: dict[str, str] | str
    result: str
    should_continue: bool = True

    def render(self) -> str:
        return render_block(self.task, self.status, self.result)


CommandHandler = Callable[[ParsedCommand], RouteResult]


class CommandRouter:
    """Central command router for ANUBIS slash commands.

    The router intentionally keeps handlers small and deterministic. External
    command systems, including the future DSL layer, can register handlers
    without changing the CLI loop.
    """

    def __init__(self, state: MutableMapping[str, Any] | None = None) -> None:
        self.state = state if state is not None else self._new_state()
        self.agents = AgentRegistry(self.state)
        self.swarm = SwarmEngine(self.agents)
        self.handlers: dict[str, CommandHandler] = {}
        self.register_defaults()

    def register(self, name: str, handler: CommandHandler) -> None:
        command_name = self.normalize_command_name(name)
        if not command_name:
            raise ValueError("command name required")
        self.handlers[command_name] = handler

    def unregister(self, name: str) -> None:
        self.handlers.pop(self.normalize_command_name(name), None)

    def register_defaults(self) -> None:
        for name, handler in {
            "/help": self._help,
            "/status": self._status,
            "/exit": self._exit,
            "/quit": self._exit,
            "/q": self._exit,
            "/build": self._build,
            "/analyze": self._analyze,
            "/research": self._research,
            "/agent": self._agent,
            "/swarm": self._swarm,
        }.items():
            self.register(name, handler)

    def route(self, raw_input: str) -> RouteResult | None:
        command = self.parse(raw_input)
        if not command.name:
            return None

        handler = self.handlers.get(command.name)
        if handler is None:
            return RouteResult(
                task="Parse command",
                status=self.agent_states,
                result=f"unknown command: {command.name}\nrun: /help",
            )
        return handler(command)

    def parse(self, raw_input: str) -> ParsedCommand:
        text = raw_input.strip()
        if not text:
            return ParsedCommand(name="")

        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()

        if not parts:
            return ParsedCommand(name="")

        name = self.normalize_command_name(parts[0])
        raw_args = text[len(parts[0]) :].strip()
        return ParsedCommand(name=name, args=parts[1:], raw_args=raw_args)

    @property
    def agent_states(self) -> dict[str, str]:
        return self.agents.snapshot()

    def _set_agent(self, name: str, status: str) -> None:
        self.agents.update(name, status)

    def _new_state(self) -> dict[str, Any]:
        return {"agents": dict(DEFAULT_STATE["agents"])}

    def normalize_command_name(self, name: str) -> str:
        return name.strip().lower()

    def _help(self, _command: ParsedCommand) -> RouteResult:
        commands = "\n".join(
            [
                "system:",
                "  /help",
                "  /status",
                "  /exit",
                "execution:",
                "  /build <task>",
                "  /analyze <input>",
                "  /research <query>",
                "agents:",
                "  /agent spawn <name>",
                "  /agent list",
                "swarm:",
                "  /swarm <goal>",
            ]
        )
        return RouteResult("Help", self.agent_states, commands)

    def _status(self, _command: ParsedCommand) -> RouteResult:
        agents = self.agent_states
        completed = sum(1 for state in agents.values() if state == "completed")
        result = "\n".join(
            [
                "runtime: ready",
                f"agents: {len(agents)}",
                f"completed: {completed}",
            ]
        )
        return RouteResult("Status", agents, result)

    def _exit(self, _command: ParsedCommand) -> RouteResult:
        return RouteResult("Shutdown ANUBIS CLI", self.agent_states, "session closed", should_continue=False)

    def _build(self, command: ParsedCommand) -> RouteResult:
        task = command.raw_args.strip()
        if not task:
            return RouteResult("Validate command", self.agent_states, "build task required")
        self._set_agent("builder", "running")
        self._set_agent("builder", "completed")
        return RouteResult(f"Build {task}", self.agent_states, f"build task accepted: {task}")

    def _analyze(self, command: ParsedCommand) -> RouteResult:
        target = command.raw_args.strip()
        if not target:
            return RouteResult("Validate command", self.agent_states, "analysis input required")
        self._set_agent("analyst", "running")
        self._set_agent("analyst", "completed")
        return RouteResult(f"Analyze {target}", self.agent_states, f"analysis prepared: {target}")

    def _research(self, command: ParsedCommand) -> RouteResult:
        query = command.raw_args.strip()
        if not query:
            return RouteResult("Validate command", self.agent_states, "research query required")
        self._set_agent("researcher", "running")
        self._set_agent("researcher", "completed")
        return RouteResult(f"Research {query}", self.agent_states, f"research brief prepared: {query}")

    def _agent(self, command: ParsedCommand) -> RouteResult:
        if not command.args:
            return RouteResult("AGENT SYSTEM", self.agent_states, "usage: /agent spawn <name> | /agent list")

        action = command.args[0].lower()
        if action == "list":
            return RouteResult("AGENT SYSTEM", self.agent_states, "ok")

        if action == "spawn":
            if len(command.args) < 2:
                return RouteResult("AGENT SYSTEM", self.agent_states, "agent name required")
            result = self.agents.spawn(command.args[1])
            return RouteResult("AGENT SYSTEM", self.agent_states, result)

        return RouteResult("AGENT SYSTEM", self.agent_states, f"unknown agent action: {action}")

    def _swarm(self, command: ParsedCommand) -> RouteResult:
        goal = command.raw_args.strip()
        if not goal:
            return RouteResult("Validate command", self.agent_states, "swarm goal required")

        result = self.swarm.run(goal)
        status = self.agent_states
        status["__logs__"] = result.render_logs()
        return RouteResult(result.goal, status, result.render_outputs())


__all__ = ["CommandHandler", "CommandRouter", "ParsedCommand", "RouteResult"]
