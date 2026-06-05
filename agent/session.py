from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from anubis.llm import OllamaClient, OllamaRouter
from anubis.memory.session import SessionMemory


SYSTEM_PROMPT = """You are Anubis, a local terminal-first coding agent.
Act like Claude Code: inspect the repository, call tools when needed, stream concise progress,
and finish with concrete work completed or a clear blocker.

Return exactly one JSON object when asked for an action:
{"intent":"final|tool","tool":"read_file|write_file|list_files|run_shell|none","args":{},"reason":"short reason"}
Do not include hidden chain-of-thought.
"""


@dataclass(frozen=True)
class AgentAction:
    intent: str
    tool: str = "none"
    args: dict[str, Any] | None = None
    reason: str = ""


class PlannerAgent:
    def plan(self, task: str, memory: SessionMemory) -> list[str]:
        text = task.lower()
        steps = ["Understand the request"]
        if any(word in text for word in ("file", "repo", "code", "test", "fix", "implement", "architecture")):
            steps.append("Inspect relevant project files")
        if any(word in text for word in ("implement", "transforme", "fix", "build", "ajoute", "crée", "create")):
            steps.append("Apply focused code changes")
        steps.append("Verify with targeted commands")
        memory.remember(f"Current plan: {'; '.join(steps)}")
        return steps


class ExecutorAgent:
    def __init__(self, *, client: OllamaClient | None = None, router: OllamaRouter | None = None) -> None:
        self.client = client or OllamaClient()
        self.router = router or OllamaRouter()

    def decide(self, task: str, memory: SessionMemory, tools: list[str]) -> AgentAction:
        heuristic = _heuristic_action(task, tools)
        if heuristic is not None:
            return heuristic
        context = memory.compact()
        prompt = (
            f"{SYSTEM_PROMPT}\n\nAvailable tools: {', '.join(tools)}\n\n"
            f"Task:\n{task}\n\nMemory:\n{context}\n\nChoose the next action."
        )
        routed = self.router.route(prompt, role="executor")
        raw = self.client.chat(routed.model, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
        return _parse_action(raw)


class ReviewerAgent:
    def review(self, task: str, result: dict[str, Any] | None, memory: SessionMemory) -> str:
        if result is None:
            return "No tool execution was needed."
        status = "passed" if result.get("success") else "failed"
        tool = result.get("tool", "unknown")
        memory.remember(f"Last verification: {tool} {status}")
        return f"{tool} verification {status}"


def _parse_action(raw: str) -> AgentAction:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        return AgentAction("final", "none", {"result": raw.strip()}, "model returned plain text")
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return AgentAction("final", "none", {"result": raw.strip()}, "model returned invalid JSON")
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    return AgentAction(
        intent=str(payload.get("intent") or "final"),
        tool=str(payload.get("tool") or "none"),
        args=args,
        reason=str(payload.get("reason") or ""),
    )


def _heuristic_action(task: str, tools: list[str]) -> AgentAction | None:
    text = task.strip()
    lower = text.lower()
    if lower.startswith("ls ") or lower in {"ls", "list files"}:
        return AgentAction("tool", "list_files", {"path": text[3:].strip() or "."}, "list requested files")
    if lower.startswith("cat "):
        return AgentAction("tool", "read_file", {"path": text[4:].strip()}, "read requested file")
    if lower.startswith("run "):
        return AgentAction("tool", "run_shell", {"cmd": text[4:].strip()}, "run requested command")
    if any(word in lower for word in ("architecture", "anti-pattern", "antipattern", "ux terminal")):
        return AgentAction("final", "none", {"result": _architecture_brief()}, "architecture request")
    return None


def _architecture_brief() -> str:
    return (
        "Architecture cible: CLI/Desktop/API -> SessionRuntime -> AgentOrchestrator -> "
        "OllamaRouter + ToolExecutionEngine + SessionMemory. "
        "UX terminal: prompt sobre, événements live, tool calls visibles, validation explicite, "
        "résumé final actionnable. Anti-patterns: boucle agent monolithique, prompts qui exécutent "
        "des effets sans tools, streaming mélangé au rendu, accès shell non borné, mémoire globale non compactée."
    )


__all__ = ["AgentAction", "ExecutorAgent", "PlannerAgent", "ReviewerAgent", "SYSTEM_PROMPT"]
