from __future__ import annotations

from dataclasses import dataclass
import re

from anubis.types import AgentContext, JSONObject, Plan, PlanStep, TaskSnapshot


@dataclass(frozen=True)
class PlanningIntent:
    label: str
    confidence: float


class DefaultPlanner:
    """Deterministic tool-only planner for the production loop foundation."""

    def plan(self, task: TaskSnapshot, context: AgentContext) -> Plan:
        goal = task["goal"]
        intent = self.understand(goal)
        steps = tuple(self._steps(goal, task.get("context", {})))
        return Plan(
            task_id=task["id"],
            goal=goal,
            steps=steps,
            metadata={
                "intent": {"label": intent.label, "confidence": intent.confidence},
                "context_chars": len(context.compressed),
            },
        )

    def understand(self, goal: str) -> PlanningIntent:
        text = goal.lower()
        if any(word in text for word in ("write", "create", "update")):
            return PlanningIntent("modify_files", 0.75)
        if any(word in text for word in ("read", "inspect", "open")):
            return PlanningIntent("inspect_files", 0.75)
        return PlanningIntent("unsupported", 0.35)

    def _steps(self, goal: str, task_context: JSONObject) -> list[PlanStep]:
        write_target = task_context.get("path")
        write_content = task_context.get("content")
        if isinstance(write_target, str) and isinstance(write_content, str):
            return [
                PlanStep(
                    id=1,
                    goal=f"Write requested content to {write_target}",
                    tool="write_file",
                    input={"path": write_target, "content": write_content},
                ),
                PlanStep(
                    id=2,
                    goal=f"Read back {write_target} to verify state",
                    tool="read_file",
                    input={"path": write_target},
                ),
            ]

        paths = _paths_from_text(goal)
        if paths:
            return [
                PlanStep(
                    id=index,
                    goal=f"Read task-relevant file {path}",
                    tool="read_file",
                    input={"path": path},
                )
                for index, path in enumerate(paths, start=1)
            ]
        return []


def _paths_from_text(text: str) -> list[str]:
    paths = re.findall(r"[\w./-]+\.[A-Za-z0-9]+", text)
    return [path.strip("./") for path in paths if ".." not in path]


__all__ = ["DefaultPlanner", "PlanningIntent"]
