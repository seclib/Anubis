from __future__ import annotations

from commands import bugbounty, cve, defense, dev, graph, osint, tools
from commands._rag import route_query
from commands.system import exit_command, help_command, status_command
from core.context import CliContext
from core.dispatcher import CommandDispatcher, CommandResult
from utils.parser import CommandParser


class CliRouter:
    def __init__(self, dispatcher: CommandDispatcher | None = None, ctx: CliContext | None = None) -> None:
        self.dispatcher = dispatcher or CommandDispatcher()
        self.ctx = ctx or CliContext()
        self.parser = CommandParser()
        self._register_defaults()

    def route(self, line: str) -> CommandResult | None:
        text = self._normalize(line)
        if not text:
            return None
        return self.dispatcher.dispatch(self.parser.parse(text), self.ctx)

    def _register_defaults(self) -> None:
        for name in ("/help",):
            self.dispatcher.register(name, help_command)
        for name in ("/status",):
            self.dispatcher.register(name, status_command)
        for name in ("/exit", "/quit", "/q"):
            self.dispatcher.register(name, exit_command)
        self.dispatcher.register("/rag", route_query)
        self.dispatcher.register("/osint", osint.handle)
        self.dispatcher.register("/cve", cve.handle)
        self.dispatcher.register("/bugbounty", bugbounty.handle)
        self.dispatcher.register("/bug", bugbounty.handle)
        self.dispatcher.register("/dev", dev.handle)
        self.dispatcher.register("/code", dev.handle)
        self.dispatcher.register("/defense", defense.handle)
        self.dispatcher.register("/graph", graph.handle)
        self.dispatcher.register("/tools", tools.handle)
        self.dispatcher.register("/tooling", tools.handle)

    def _normalize(self, line: str) -> str:
        text = line.strip()
        if not text:
            return ""
        if text in {"help", "status", "exit", "quit"}:
            return f"/{text}"
        return text
