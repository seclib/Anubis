from __future__ import annotations

from commands._rag import query_rag
from core.context import CliContext
from core.dispatcher import CommandResult
from utils.parser import ParsedCommand


def handle(command: ParsedCommand, ctx: CliContext) -> CommandResult:
    return query_rag("dev", command, ctx)
