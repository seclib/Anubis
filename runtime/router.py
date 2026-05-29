"""Decision routing between LLM responses, tools, and final answers.

The router is deliberately small and stateless. It does not call tools or LLMs;
it only classifies the next execution target so the agent loop can stay explicit
and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Collection, Mapping


class Route(StrEnum):
    PLAN = "plan"
    TOOL = "tool"
    LLM = "llm"
    FINAL = "final"
    INVALID = "invalid"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str
    tool: str = ""
    args: Mapping[str, Any] | None = None


def route_agent_action(
    action: Mapping[str, Any] | None,
    available_tools: Collection[str],
) -> RouteDecision:
    """Classify a parsed agent action without executing side effects."""
    if not isinstance(action, Mapping):
        return RouteDecision(Route.INVALID, "Action is not a mapping")

    intent = str(action.get("intent") or action.get("action") or "act").lower()
    tool = str(action.get("tool") or "").strip()
    args = action.get("args")
    normalized_args = args if isinstance(args, Mapping) else {}

    if intent == "plan":
        return RouteDecision(Route.PLAN, "Agent requested plan update", tool=tool, args=normalized_args)
    if intent == "final" or tool in {"final", "none"}:
        return RouteDecision(Route.FINAL, "Agent requested final answer", tool=tool, args=normalized_args)
    if tool and tool in set(available_tools):
        return RouteDecision(Route.TOOL, "Agent selected a registered tool", tool=tool, args=normalized_args)
    if tool:
        return RouteDecision(Route.INVALID, f"Unknown tool: {tool}", tool=tool, args=normalized_args)
    return RouteDecision(Route.LLM, "No tool selected; continue LLM reasoning", args=normalized_args)


def route_user_input(text: str) -> RouteDecision:
    """Classify raw CLI input before it reaches the agent runtime."""
    value = text.strip()
    if not value:
        return RouteDecision(Route.INVALID, "Empty input")
    if value.startswith("/"):
        return RouteDecision(Route.TOOL, "CLI command input", tool=value.split(maxsplit=1)[0])
    return RouteDecision(Route.LLM, "Natural-language task")


__all__ = ["Route", "RouteDecision", "route_agent_action", "route_user_input"]
