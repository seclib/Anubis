from __future__ import annotations

from cli_mvp.commands.context import CommandContext
from cli_mvp.commands.helpers import require_raw
from cli_mvp.models import Command, RenderBlock


def swarm_command(command: Command, ctx: CommandContext) -> None:
    goal = require_raw(command, ctx, "swarm goal required")
    if goal is None:
        return
    result = ctx.swarm.run(goal)
    ctx.renderer.block(RenderBlock(task=f"Swarm {goal}", status=ctx.agents.states, result=result))
