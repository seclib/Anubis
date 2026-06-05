"""Unified command router for the ANUBIS CLI.

This replaces the previous ``UnifiedCommandRouter`` that delegated domain
commands to the legacy ``anubis-cli/`` package via ``anubis_cli_loader``.
All domain RAG commands are now handled natively through
``anubis.cli.commands.rag_domains``.
"""
from __future__ import annotations

from dataclasses import dataclass

from anubis.cli.commands.rag_domains import DOMAIN_HANDLERS
from anubis.cli.router import CliRouter


LEGACY_CLI_COMMANDS = {
    "console",
    "exec",
    "run",
    "repl",
    "sync",
    "orchestrate",
}


@dataclass(frozen=True)
class CommandRouteResult:
    text: str
    should_continue: bool = True

    def render(self) -> str:
        return self.text


class UnifiedCommandRouter:
    """CLI command router with native domain RAG support.

    Domain RAG slash commands (``/rag``, ``/osint``, ``/cve``, etc.) are
    handled directly through ``DOMAIN_HANDLERS`` without relying on the
    legacy ``anubis-cli`` package.
    """

    def __init__(self, cli_router: CliRouter | None = None) -> None:
        self.cli_router = cli_router or CliRouter()

    def route(self, line: str) -> CommandRouteResult | None:
        text = line.strip()
        if not text:
            return None

        command = text.split(maxsplit=1)[0].strip().lower()

        # Domain RAG commands handled natively
        handler = DOMAIN_HANDLERS.get(command)
        if handler is not None:
            query = text[len(command):].strip()
            result = handler(query)
            rendered = _render_result(result)
            return CommandRouteResult(rendered, result.get("should_continue", True))

        # Everything else goes through the package-local CliRouter
        result = self.cli_router.route(text)
        if result is None:
            return None
        return CommandRouteResult(result.text, result.should_continue)


def _render_result(result: dict) -> str:
    """Render a domain handler result dict in the TASK/STATUS/RESULT format."""
    task = str(result.get("task", ""))
    status = result.get("status", "")
    body = str(result.get("result", ""))

    if isinstance(status, dict):
        status_text = "\n".join(f"- {k}: {v}" for k, v in status.items())
    else:
        status_text = str(status) if status else "ready"

    return "\n".join([
        "TASK:",
        task or "none",
        "",
        "STATUS:",
        status_text or "none",
        "",
        "RESULT:",
        body or "none",
        "",
    ])


__all__ = ["CommandRouteResult", "LEGACY_CLI_COMMANDS", "UnifiedCommandRouter"]
