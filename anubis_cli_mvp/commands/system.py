from __future__ import annotations

from anubis_cli_mvp.commands.context import CommandContext
from anubis_cli_mvp.models import Command, RenderBlock


def help_command(_command: Command, ctx: CommandContext) -> None:
    result = "\n".join(
        [
            "/help",
            "/status",
            "/build <task>",
            "/analyze <input>",
            "/research <query>",
            "/agent spawn <name>",
            "/agent list",
            "/swarm <goal>",
            "/memory save <data>",
            "/memory query <input>",
            "/memory clear",
            "/exit",
        ]
    )
    ctx.renderer.block(RenderBlock(task="Show command reference", status=ctx.agents.states, result=result))


def status_command(_command: Command, ctx: CommandContext) -> None:
    ctx.renderer.block(RenderBlock(task="Show system status", status=ctx.agents.states, result="system ready"))


def exit_command(_command: Command, ctx: CommandContext) -> None:
    ctx.running = False
    ctx.renderer.block(RenderBlock(task="Shutdown ANUBIS CLI", status=ctx.agents.states, result="session closed"))
