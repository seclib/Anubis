from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Mapping, Protocol


PHASE1_TOOLS = {
    "read_file",
    "write_file",
    "search_codebase",
    "run_command",
    "git_diff",
    "git_commit",
}


class PlannerLLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class AgentContext:
    task: str
    items: list[dict[str, Any]] = field(default_factory=list)
    compressed: str = ""
    retry_feedback: str = ""


@dataclass(frozen=True)
class PlanStep:
    id: int
    goal: str
    tool: str | None = None
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    task: str
    context: AgentContext
    steps: list[PlanStep]


class Planner:
    def __init__(self, llm: PlannerLLM | None = None) -> None:
        self.llm = llm

    def plan(self, task: str, context: AgentContext) -> Plan:
        if self.llm is not None:
            steps = self._llm_steps(task, context)
            if steps:
                return Plan(task=task, context=context, steps=steps)
        return Plan(task=task, context=context, steps=self._fallback_steps(task, context))

    def _llm_steps(self, task: str, context: AgentContext) -> list[PlanStep]:
        prompt = {
            "role": "planner",
            "rules": [
                "Return JSON only.",
                "Use only these tools: read_file, write_file, search_codebase, run_command, git_diff, git_commit.",
                "Every tool call must use the exact input object required by that tool.",
                "No UI work.",
            ],
            "task": task,
            "context": asdict(context),
            "output_schema": {
                "steps": [
                    {
                        "id": 1,
                        "goal": "short goal",
                        "tool": "search_codebase",
                        "input": {"query": "term"},
                    }
                ]
            },
        }
        assert self.llm is not None
        payload = _parse_json(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        return self._steps_from_payload(payload)

    def _steps_from_payload(self, payload: Mapping[str, Any]) -> list[PlanStep]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            return []
        steps: list[PlanStep] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, Mapping):
                continue
            goal = str(raw_step.get("goal") or "").strip()
            if not goal:
                continue
            tool = raw_step.get("tool")
            tool_name = str(tool) if tool else None
            if tool_name is not None and tool_name not in PHASE1_TOOLS:
                continue
            tool_input = raw_step.get("input", raw_step.get("args", {}))
            steps.append(
                PlanStep(
                    id=int(raw_step.get("id") or index),
                    goal=goal,
                    tool=tool_name,
                    input=dict(tool_input) if isinstance(tool_input, Mapping) else {},
                )
            )
        return steps

    def _fallback_steps(self, task: str, context: AgentContext) -> list[PlanStep]:
        steps: list[PlanStep] = []
        context_paths = _paths_from_context(context)
        for path in context_paths[:3]:
            steps.append(
                PlanStep(
                    id=len(steps) + 1,
                    goal=f"Read context-ranked file {path}",
                    tool="read_file",
                    input={"path": path},
                )
            )
        if not steps:
            steps.append(
                PlanStep(
                    id=1,
                    goal="Search the codebase for task-relevant context",
                    tool="search_codebase",
                    input={"query": _search_query(task)},
                )
            )

        paths = [path for path in _paths_from_text(task) if path not in context_paths]
        for path in paths[:3]:
            steps.append(
                PlanStep(
                    id=len(steps) + 1,
                    goal=f"Read referenced file {path}",
                    tool="read_file",
                    input={"path": path},
                )
            )
        if "git" in task.lower() or "diff" in task.lower() or context.retry_feedback:
            steps.append(
                PlanStep(
                    id=len(steps) + 1,
                    goal="Inspect current Git diff",
                    tool="git_diff",
                    input={},
                )
            )
        steps.append(PlanStep(id=len(steps) + 1, goal="Verify whether the task is complete"))
        return steps


def _parse_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _search_query(task: str) -> str:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", task)
    return " ".join(words[:6]) or task.strip()


def _paths_from_text(text: str) -> list[str]:
    candidates = re.findall(r"[\w./-]+\.[A-Za-z0-9]+", text)
    return [candidate.strip("./") for candidate in candidates if ".." not in candidate]


def _paths_from_context(context: AgentContext) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in context.items:
        output = item.get("output") if isinstance(item, Mapping) else None
        if not isinstance(output, Mapping):
            continue
        chunks = output.get("chunks")
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                continue
            path = str(chunk.get("path") or "").strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


__all__ = ["AgentContext", "PHASE1_TOOLS", "Plan", "Planner", "PlannerLLM", "PlanStep"]
