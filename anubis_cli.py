#!/usr/bin/env python3
"""ANUBIS CLI runtime entry point.

Minimal terminal shell for the ANUBIS project. The file owns startup and input
loop behavior, then delegates command execution to the project's router when it
is available.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.ux import render_block


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class RuntimeHooks:
    command_router: Any | None = None
    handle_command: Callable[[str, Any], bool] | None = None
    run_task: Callable[[str], None] | None = None
    conversation: Any | None = None
    configure_logging: Callable[[], None] | None = None


class FallbackRouter:
    """Small router used when project internals are unavailable."""

    def route(self, text: str) -> bool:
        command, _, args = text.partition(" ")
        command = command.lower()
        args = args.strip()

        if command in {"/exit", "/quit", "/q"}:
            return False
        if command == "/help":
            self.help()
            return True
        if command == "/status":
            self.status()
            return True

        task = args if command.startswith("/") else text
        self._block("Route command", "ready", f"accepted: {task or command}")
        return True

    def _block(self, task: str, status: str, result: str) -> None:
        sys.stdout.write(render_block(task, status, result))

    def help(self) -> None:
        self._block(
            "Show command reference",
            "ready",
            "\n".join(
                [
                    "/help",
                    "/status",
                    "/exit",
                    "/run <task>",
                    "/exec <command>",
                    "<task>",
                ]
            ),
        )

    def status(self) -> None:
        self._block("Show system status", "ready", "system ready")


class ProjectRouter:
    """Adapter around the existing ANUBIS command layer."""

    def __init__(self, hooks: RuntimeHooks) -> None:
        self.hooks = hooks
        self.fallback = FallbackRouter()

    def route(self, text: str) -> bool:
        command = text.split(None, 1)[0].lower()

        if self.hooks.command_router is not None and text.startswith("/"):
            routed = self.hooks.command_router.route(text)
            if routed is None:
                return True
            sys.stdout.write(routed.render())
            return bool(routed.should_continue)

        if self.hooks.handle_command is not None and text.startswith("/"):
            return bool(self.hooks.handle_command(text, self.hooks.conversation))

        if self.hooks.run_task is not None:
            self.hooks.run_task(text)
            return True

        return self.fallback.route(text)


class AnubisRuntime:
    def __init__(self, *, boot_delay: float = 0.12) -> None:
        self.boot_delay = boot_delay
        self.router = ProjectRouter(load_runtime_hooks())

    def boot(self) -> None:
        for stage in (
            "Core loading",
            "Hermes engine loading",
            "Memory system loading",
            "Agent runtime loading",
            "System ready",
        ):
            print(stage)
            if self.boot_delay > 0:
                time.sleep(self.boot_delay)
        print()

    def run(self) -> None:
        while True:
            try:
                text = input("anubis > ").strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                self.shutdown()
                break

            if not text:
                continue
            if not self.router.route(text):
                break

    def run_commands(self, commands: list[str]) -> None:
        for command in commands:
            text = command.strip()
            if not text:
                continue
            if not self.router.route(text):
                break

    def shutdown(self) -> None:
        sys.stdout.write(render_block("Shutdown ANUBIS CLI", "stopped", "session closed"))


def load_runtime_hooks() -> RuntimeHooks:
    hooks = RuntimeHooks()

    try:
        from cli.ui import configure_logging

        hooks.configure_logging = configure_logging
        configure_logging()
    except Exception:
        pass

    try:
        from cli.router import CommandRouter

        hooks.command_router = CommandRouter()
    except Exception:
        pass

    try:
        from cli.commands import handle_command, run_agent_task
        from cli.session import CLI_SYSTEM_PROMPT, ConversationMemory

        hooks.handle_command = handle_command
        hooks.run_task = run_agent_task
        hooks.conversation = ConversationMemory(CLI_SYSTEM_PROMPT)
    except Exception:
        pass

    return hooks


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ANUBIS CLI")
    parser.add_argument("--fast", action="store_true", help="disable boot delay")
    parser.add_argument("--no-boot", action="store_true", help="skip boot sequence")
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
    runtime = AnubisRuntime(boot_delay=0 if args.fast else 0.12)

    if not args.no_boot:
        runtime.boot()

    if args.command:
        runtime.run_commands(args.command)
        return 0

    runtime.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
