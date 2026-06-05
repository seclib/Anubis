"""Unified command router for the ANUBIS CLI Phase 1 surface."""
from __future__ import annotations

import os
import sys


LEGACY_CLI_COMMANDS = {
    "console",
    "exec",
    "run",
    "repl",
    "sync",
    "orchestrate",
}


class CommandRouteResult:
    def __init__(self, text: str, should_continue: bool = True) -> None:
        self.text = text
        self.should_continue = should_continue

    def render(self) -> str:
        return self.text


class UnifiedCommandRouter:
    """CLI command router with native domain RAG support.

    Domain RAG slash commands (``/rag``, ``/osint``, ``/cve``, etc.) are
    handled directly through ``DOMAIN_HANDLERS`` without relying on the
    legacy ``anubis-cli`` package.
    """

    def __init__(self, cli_router: object | None = None) -> None:
        self.cli_router = cli_router or _load_cli_router()()
        self.domain_handlers = _load_domain_handlers()

    def route(self, line: str) -> CommandRouteResult | None:
        text = line.strip()
        if not text:
            return None

        command = text.split(maxsplit=1)[0].strip().lower()

        # Domain RAG commands handled natively
        handler = self.domain_handlers.get(command)
        if handler is not None:
            query = text[len(command):].strip()
            result = handler(query)
            rendered = _render_result(result)
            return CommandRouteResult(rendered, result.get("should_continue", True))

        # Everything else goes through the package-local CliRouter
        result = self.cli_router.route(text)
        if result is None:
            return None
        rendered = result.text if hasattr(result, "text") else result.render()
        return CommandRouteResult(rendered, result.should_continue)


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _without_project_root(callback):
    root = _project_root()
    original_path = list(sys.path)
    sys.path = [
        path
        for path in sys.path
        if path not in {"", root}
        and os.path.abspath(path or os.getcwd()) != root
    ]
    try:
        return callback()
    finally:
        sys.path = original_path


def _load_cli_router():
    def load():
        from cli.core.router import CliRouter

        return CliRouter

    return _without_project_root(load)


def _load_domain_handlers():
    def load():
        from cli.commands.rag_domains import DOMAIN_HANDLERS

        return DOMAIN_HANDLERS

    return _without_project_root(load)


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
