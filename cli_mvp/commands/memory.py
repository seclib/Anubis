from __future__ import annotations

from cli_mvp.commands.context import CommandContext
from cli_mvp.models import Command, RenderBlock


def memory_command(command: Command, ctx: CommandContext) -> None:
    if not command.args:
        result = "usage: /memory save <data> | /memory query <input> | /memory clear"
        ctx.renderer.block(RenderBlock(task="Memory command", status=ctx.agents.states, result=result))
        return

    action = command.args[0].lower()
    payload = command.raw_args[len(command.args[0]) :].strip()

    if action == "save":
        result = ctx.memory.save(payload) if payload else "memory data required"
        ctx.renderer.block(RenderBlock(task="Save memory", status=ctx.agents.states, result=result))
        return

    if action == "query":
        matches = ctx.memory.query(payload) if payload else []
        result = "\n".join(matches) if matches else "no memory matches"
        ctx.renderer.block(RenderBlock(task="Query memory", status=ctx.agents.states, result=result))
        return

    if action == "clear":
        ctx.renderer.block(RenderBlock(task="Clear memory", status=ctx.agents.states, result=ctx.memory.clear()))
        return

    ctx.renderer.block(RenderBlock(task="Memory command", status=ctx.agents.states, result=f"unknown memory action: {action}"))
