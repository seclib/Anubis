from __future__ import annotations

from anubis_cli_mvp.agents import AgentManager
from anubis_cli_mvp.commands.context import CommandContext
from anubis_cli_mvp.commands.registry import CommandRegistry
from anubis_cli_mvp.dsl import CommandParser
from anubis_cli_mvp.memory import MemoryStore
from anubis_cli_mvp.models import RenderBlock
from anubis_cli_mvp.renderer import Renderer
from anubis_cli_mvp.swarm import SwarmEngine


class AnubisCLI:
    def __init__(self, *, boot_delay: float = 0.12) -> None:
        agents = AgentManager()
        self.renderer = Renderer()
        self.parser = CommandParser()
        self.registry = CommandRegistry()
        self.context = CommandContext(
            renderer=self.renderer,
            agents=agents,
            memory=MemoryStore(),
            swarm=SwarmEngine(agents),
        )
        self.boot_delay = boot_delay

    @property
    def running(self) -> bool:
        return self.context.running

    def boot(self) -> None:
        self.renderer.boot(self.boot_delay)

    def loop(self) -> None:
        while self.running:
            try:
                text = input("anubis > ")
            except EOFError:
                self.renderer.line()
                break
            except KeyboardInterrupt:
                self.renderer.line()
                self.execute("/exit")
                break
            self.execute(text)

    def execute(self, text: str) -> None:
        command = self.parser.parse(text)
        if not command.name:
            return

        handler = self.registry.get(command.name)
        if handler is None:
            self.renderer.block(
                RenderBlock(
                    task="Parse command",
                    status=self.context.agents.states,
                    result=f"unknown command: {command.name}. run /help",
                )
            )
            return

        handler(command, self.context)
