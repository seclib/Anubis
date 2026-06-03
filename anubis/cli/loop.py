from __future__ import annotations

from collections.abc import Callable

from anubis.cli.output import write_output
from anubis.cli.router import CliRouter

PROMPT = "anubis >"


def run_loop(
    router: CliRouter | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = write_output,
) -> int:
    cli_router = router or CliRouter()
    while True:
        try:
            line = input_fn(PROMPT)
        except EOFError:
            output_fn("")
            return 0
        except KeyboardInterrupt:
            output_fn("")
            return 130

        routed = cli_router.route(line)
        if routed is None:
            continue
        output_fn(routed.text)
        if not routed.should_continue:
            return 0


def run_commands(commands: list[str], router: CliRouter | None = None, output_fn: Callable[[str], None] = write_output) -> int:
    cli_router = router or CliRouter()
    for command in commands:
        routed = cli_router.route(command)
        if routed is None:
            continue
        output_fn(routed.text)
        if not routed.should_continue:
            return 0
    return 0


__all__ = ["PROMPT", "run_commands", "run_loop"]
