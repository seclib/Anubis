from __future__ import annotations

from cli_mvp.commands.context import CommandContext
from cli_mvp.commands.helpers import require_raw
from cli_mvp.models import Command, RenderBlock


def build_command(command: Command, ctx: CommandContext) -> None:
    task = require_raw(command, ctx, "build task required")
    if task is None:
        return
    result = ctx.agents.run("builder", lambda: f"build task completed: {task}")
    ctx.renderer.block(RenderBlock(task=f"Build {task}", status=ctx.agents.states, result=result))


def analyze_command(command: Command, ctx: CommandContext) -> None:
    target = require_raw(command, ctx, "analysis input required")
    if target is None:
        return
    result = ctx.agents.run("analyst", lambda: f"analysis completed: {target}")
    ctx.renderer.block(RenderBlock(task=f"Analyze {target}", status=ctx.agents.states, result=result))


def research_command(command: Command, ctx: CommandContext) -> None:
    query = require_raw(command, ctx, "research query required")
    if query is None:
        return
    result = ctx.agents.run("researcher", lambda: f"research completed: {query}")
    ctx.renderer.block(RenderBlock(task=f"Research {query}", status=ctx.agents.states, result=result))
