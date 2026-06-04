from __future__ import annotations

import argparse

from cli_mvp.app import AnubisCLI


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ANUBIS minimal terminal AI interface")
    parser.add_argument("--fast", action="store_true", help="disable boot sequence delay")
    parser.add_argument("--no-boot", action="store_true", help="skip boot sequence output")
    parser.add_argument(
        "--command",
        "-c",
        action="append",
        default=[],
        help="execute command non-interactively; may be passed multiple times",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cli = AnubisCLI(boot_delay=0 if args.fast else 0.12)

    if not args.no_boot:
        cli.boot()

    if args.command:
        for command in args.command:
            if not cli.running:
                break
            cli.execute(command)
        return 0

    cli.loop()
    return 0
