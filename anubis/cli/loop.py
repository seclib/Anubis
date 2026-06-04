from __future__ import annotations

from collections.abc import Callable

from anubis.cli.formatter import format_error, write_output
from anubis.cli.prompt import PROMPT, render_prompt
from anubis.cli.router import CliRouter
from anubis.cli.session_commands import SessionCommandController
from anubis.cli.terminal import TerminalRenderer
from anubis.core.session import SessionRuntime


def run_loop(
    router: CliRouter | None = None,
    session: SessionRuntime | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = write_output,
) -> int:
    cli_router = router or CliRouter()
    runtime = session or SessionRuntime()
    renderer = TerminalRenderer(None if output_fn is write_output else output_fn)
    session_commands = SessionCommandController(runtime)
    while True:
        try:
            line = input_fn(render_prompt())
        except EOFError:
            output_fn("")
            return 0
        except KeyboardInterrupt:
            output_fn("")
            return 130

        session_result = session_commands.route(line)
        if session_result is not None:
            output_fn(session_result.text)
            if not session_result.should_continue:
                return 0
            continue

        if is_agent_turn(line):
            try:
                renderer.render_stream(runtime.run(line.strip()))
            except Exception as exc:
                output_fn(format_error("Agent execution", exc))
            continue

        try:
            routed = cli_router.route(line)
        except Exception as exc:
            output_fn(format_error("Command execution", exc))
            continue
        if routed is None:
            continue
        output_fn(routed.text)
        if not routed.should_continue:
            return 0


def run_commands(
    commands: list[str],
    router: CliRouter | None = None,
    output_fn: Callable[[str], None] = write_output,
    session: SessionRuntime | None = None,
) -> int:
    cli_router = router or CliRouter()
    runtime = session or SessionRuntime()
    renderer = TerminalRenderer(None if output_fn is write_output else output_fn)
    session_commands = SessionCommandController(runtime)
    for command in commands:
        if is_agent_turn(command):
            try:
                renderer.render_stream(runtime.run(command.strip()))
            except Exception as exc:
                output_fn(format_error("Agent execution", exc))
                return 1
            continue
        session_result = session_commands.route(command)
        if session_result is not None:
            output_fn(session_result.text)
            if not session_result.should_continue:
                return 0
            continue

        try:
            routed = cli_router.route(command)
        except Exception as exc:
            output_fn(format_error("Command execution", exc))
            return 1
        if routed is None:
            continue
        output_fn(routed.text)
        if not routed.should_continue:
            return 0
    return 0


def is_agent_turn(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if text.startswith("/"):
        return False
    return text.lower() not in {"help", "status", "swarm", "agent", "exit", "quit", "q"}


__all__ = ["PROMPT", "is_agent_turn", "run_commands", "run_loop"]
