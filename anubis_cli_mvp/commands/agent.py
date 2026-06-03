from __future__ import annotations

from anubis_cli_mvp.commands.context import CommandContext
from anubis_cli_mvp.models import Command, RenderBlock


def agent_command(command: Command, ctx: CommandContext) -> None:
    if not command.args:
        ctx.renderer.block(
            RenderBlock(
                task="Agent command",
                status=ctx.agents.states,
                result="usage: /agent spawn <name> | /agent list",
            )
        )
        return

    action = command.args[0].lower()
    if action == "list":
        ctx.renderer.block(RenderBlock(task="List agents", status=ctx.agents.list_agents(), result="agents listed"))
        return

    if action == "spawn":
        result = ctx.agents.spawn(command.args[1]) if len(command.args) > 1 else "agent name required"
        ctx.renderer.block(RenderBlock(task="Spawn agent", status=ctx.agents.states, result=result))
        return

    ctx.renderer.block(
        RenderBlock(task="Agent command", status=ctx.agents.states, result=f"unknown agent action: {action}")
    )
