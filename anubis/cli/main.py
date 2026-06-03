from __future__ import annotations

import argparse

from anubis.cli.loop import run_commands, run_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ANUBIS CLI")
    parser.add_argument("command", nargs="*", help="command to execute; starts interactive mode when omitted")
    parser.add_argument("-c", "--command", dest="commands", action="append", default=[], help="execute a command")
    parser.add_argument("--fast", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-boot", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tools", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-stream", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commands = list(args.commands)
    if args.command:
        commands.append(" ".join(args.command))
    if commands:
        return run_commands(commands)
    return run_loop()


if __name__ == "__main__":
    raise SystemExit(main())
