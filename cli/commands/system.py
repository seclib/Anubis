from __future__ import annotations

from cli.core.context import CliContext
from cli.core.dispatcher import CommandResult
from cli.utils.parser import ParsedCommand


def help_command(_command: ParsedCommand, _ctx: CliContext) -> CommandResult:
    return CommandResult(
        "Help",
        "ready",
        "\n".join(
            [
                "system:",
                "  /help",
                "  /status",
                "  /exit",
                "agent:",
                "  /run <task>",
                "  /sync",
                "rag:",
                "  /rag <query>",
                "  /osint <query>",
                "  /cve <query>",
                "  /bugbounty <query>",
                "  /dev <query>",
                "  /defense <query>",
                "  /graph <query>",
                "  /tools <query>",
            ]
        ),
    )


def status_command(_command: ParsedCommand, ctx: CliContext) -> CommandResult:
    return CommandResult(
        "Status",
        "ready",
        "\n".join(
            [
                f"model: {ctx.config.model}",
                f"ollama: {ctx.config.ollama_url}",
                f"qdrant: {ctx.config.qdrant_url}",
                f"state: {ctx.config.state_dir}",
            ]
        ),
    )


def exit_command(_command: ParsedCommand, _ctx: CliContext) -> CommandResult:
    return CommandResult("Shutdown ANUBIS CLI", "ready", "session closed", should_continue=False)
