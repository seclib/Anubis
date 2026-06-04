from __future__ import annotations

from cli_mvp.commands.context import CommandContext
from cli_mvp.models import Command, RenderBlock


def require_raw(command: Command, ctx: CommandContext, message: str) -> str | None:
    value = command.raw_args.strip()
    if value:
        return value
    ctx.renderer.block(RenderBlock(task="Validate command", status=ctx.agents.states, result=message))
    return None
