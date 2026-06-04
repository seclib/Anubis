from __future__ import annotations

from dataclasses import dataclass

from anubis.cli.formatter import format_output
from anubis.core.router import CommandRouter, RouteResult


@dataclass(frozen=True)
class CliRouteResult:
    text: str
    should_continue: bool = True


class CliRouter:
    def __init__(self, router: CommandRouter | None = None) -> None:
        self.router = router or CommandRouter()

    def route(self, line: str) -> CliRouteResult | None:
        command = normalize_input(line)
        if not command:
            return None
        result = self.router.route(command)
        if result is None:
            return None
        return CliRouteResult(render_route_result(result), result.should_continue)


def normalize_input(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if text in {"help", "status", "swarm", "agent"}:
        return f"/{text}"
    if not text.startswith("/"):
        return f"/build {text}"
    return text


def render_route_result(result: RouteResult) -> str:
    return format_output(result.task, result.status, result.result)


__all__ = ["CliRouteResult", "CliRouter", "normalize_input", "render_route_result"]
