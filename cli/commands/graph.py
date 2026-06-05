from __future__ import annotations

from cli.commands._rag import query_rag
from cli.core.context import CliContext
from cli.core.dispatcher import CommandResult
from cli.utils.parser import ParsedCommand


def handle(command: ParsedCommand, ctx: CliContext) -> CommandResult:
    return query_rag("graph", command, ctx)
