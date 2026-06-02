from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import json
from typing import Any

from backend.agent.llm import LLM
from backend.agent.multi_agent import Critic, Executor, Planner
from backend.rag.indexer import RagIndexer
from backend.vault.service import VaultService


class AsyncAgentLoop:
    def __init__(self, llm: LLM | None = None, max_rounds: int = 2) -> None:
        self.planner = Planner(llm=llm)
        self.executor = Executor(llm=llm)
        self.critic = Critic(llm=llm)
        self.vault = VaultService()
        self.indexer = RagIndexer()
        self.max_rounds = max_rounds

    async def run(self, task: str) -> dict[str, Any]:
        feedback = ""
        history: list[dict[str, Any]] = []
        for round_index in range(1, self.max_rounds + 1):
            plan = await asyncio.to_thread(self.planner.plan, task, feedback)
            executor_output = await asyncio.to_thread(self.executor.execute, plan)
            critique = await asyncio.to_thread(self.critic.critique, task, plan, executor_output)
            history.append(
                {
                    "round": round_index,
                    "plan": {
                        "task": plan.task,
                        "context": plan.context,
                        "steps": [asdict(step) for step in plan.steps],
                    },
                    "executor_output": asdict(executor_output),
                    "critique": asdict(critique),
                }
            )
            if critique.accepted or not critique.retry:
                break
            feedback = critique.reason

        memory_path = await asyncio.to_thread(self._store_result, task, history)
        return {
            "task": task,
            "accepted": history[-1]["critique"]["accepted"],
            "answer": self._answer(history),
            "memory_path": memory_path,
            "history": history,
        }

    def _store_result(self, task: str, history: list[dict[str, Any]]) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = f"agent-runs/{timestamp}-async.md"
        content = "\n".join(
            [
                f"# Agent run {timestamp}",
                "",
                "## task",
                task.strip(),
                "",
                "## answer",
                self._answer(history),
                "",
                "## retrieved context",
                self._context_lines(history),
                "",
                "## retrieved skills",
                "- none",
                "",
                "## actions",
                f"```json\n{json.dumps(self._actions(history), indent=2)}\n```",
                "",
                "## loop",
                f"```json\n{json.dumps(history, indent=2)}\n```",
                "",
            ]
        )
        self.vault.write_note(path, content)
        self.indexer.index_note(path)
        return path

    def _answer(self, history: list[dict[str, Any]]) -> str:
        last = history[-1]
        executor_output = last.get("executor_output", {})
        draft = str(executor_output.get("draft_response") or "")
        if not draft:
            return "No execution results."
        return draft

    def _context_lines(self, history: list[dict[str, Any]]) -> str:
        paths = []
        for round_item in history:
            for chunk in round_item.get("plan", {}).get("context", []):
                path = chunk.get("path")
                if path and path not in paths:
                    paths.append(path)
        return "\n".join(f"- {path}" for path in paths) or "- none"

    def _actions(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actions = []
        for round_item in history:
            executor_output = round_item.get("executor_output", {})
            for result in executor_output.get("step_results", []):
                step = result.get("step", {})
                if step.get("tool"):
                    actions.append({"tool": step.get("tool"), "args": step.get("args", {}), "ok": result.get("ok")})
        return actions
