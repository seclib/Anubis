from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from anubis.core.session import SessionRuntime

from backend.agent.memory import MarkdownMemory
from backend.agent.shadow import ShadowAgentRunner, ShadowRequest
from backend.agent.tools import AgentTools
from backend.skills.parser import SkillRepository


logger = logging.getLogger("anubis.agent.loop")


class AgentLoop:
    """HTTP compatibility facade over the unified Anubis session core.

    Decision-making belongs to `anubis.core.session.SessionRuntime`. This class
    keeps the legacy `/agent/chat`, `/assistant/chat`, and `/agent_query`
    response contract while limiting itself to retrieval, persistence, and
    response shaping.
    """

    def __init__(
        self,
        runtime: SessionRuntime | None = None,
        max_iterations: int = 2,
        shadow_runner: ShadowAgentRunner | None = None,
    ) -> None:
        self.runtime = runtime or SessionRuntime()
        self.tools = AgentTools()
        self.memory = MarkdownMemory()
        self.skills = SkillRepository()
        self.max_iterations = max_iterations
        self.shadow_runner = shadow_runner or ShadowAgentRunner()

    def chat(self, message: str) -> dict[str, object]:
        if message.lower().startswith("remember:"):
            target = self.memory.inject(message.split(":", 1)[1].strip())
            self.tools.reindex_memory()
            result = {
                "answer": f"Knowledge stored in {target}.",
                "chunks_used": [],
                "skills_used": [],
                "actions": [{"tool": "write_note", "result": {"path": target}}],
                "memory_suggestion": None,
            }
            self._submit_shadow(message, "", result)
            return result

        chunks = self.tools.rag_query(message)
        skills = self.skills.search(message)
        core_task = _task_with_context(message, chunks, skills)
        events = list(self.runtime.run(core_task))
        answer = _answer_from_events(events) or _answer_from_chunks(message, chunks, skills)
        actions = _actions_from_events(events)
        memory_path = self._store_run(message, answer, chunks, skills, actions)

        result = {
            "answer": answer,
            "chunks_used": chunks,
            "skills_used": [skill.as_context() for skill in skills],
            "actions": actions,
            "memory_path": memory_path,
            "memory_suggestion": self._memory_suggestion(message, chunks),
        }
        self._submit_shadow(message, _shadow_context(chunks, skills), result)
        return result

    def _store_run(
        self,
        message: str,
        answer: str,
        chunks: list[dict[str, object]],
        skills: list[object],
        actions: list[dict[str, object]],
    ) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = f"agent-runs/{timestamp}.md"
        used_paths = sorted({str(chunk.get("path")) for chunk in chunks if chunk.get("path")})
        used_skills = [str(getattr(skill, "name", "")) for skill in skills]
        content = "\n".join(
            [
                f"# Agent run {timestamp}",
                "",
                "## task",
                message.strip(),
                "",
                "## answer",
                answer.strip(),
                "",
                "## retrieved context",
                "\n".join(f"- {path}" for path in used_paths) or "- none",
                "",
                "## retrieved skills",
                "\n".join(f"- {name}" for name in used_skills if name) or "- none",
                "",
                "## actions",
                f"```json\n{json.dumps(actions, indent=2)}\n```",
                "",
            ]
        )
        self.memory.vault.write_note(path, content)
        try:
            self.tools.reindex_memory()
        except Exception as exc:  # pragma: no cover - qdrant availability varies
            logger.warning("failed to reindex after agent run: %s", exc)
        return path

    def _memory_suggestion(self, message: str, chunks: list[dict[str, object]]) -> str | None:
        if chunks or len(message.strip()) < 40:
            return None
        return "This may be new information worth saving as a note."

    def _submit_shadow(self, message: str, context: str, result: dict[str, object]) -> None:
        try:
            self.shadow_runner.submit(
                ShadowRequest(
                    prompt=message,
                    context=context,
                    active_response=dict(result),
                    source="backend.agent.loop",
                )
            )
        except Exception as exc:  # pragma: no cover - shadow must never affect active traffic
            logger.warning("failed to submit shadow agent run: %s", exc)


def _task_with_context(message: str, chunks: list[dict[str, object]], skills: list[object]) -> str:
    context = _format_context(chunks)
    skill_text = "\n\n".join(skill.as_context() for skill in skills) or "No matching skill found."
    return (
        "Use the retrieved context as evidence. Do not execute actions outside the available tools.\n\n"
        f"User request:\n{message}\n\n"
        f"Retrieved context:\n{context}\n\n"
        f"Relevant skills:\n{skill_text}"
    )


def _shadow_context(chunks: list[dict[str, object]], skills: list[object]) -> str:
    skill_text = "\n\n".join(skill.as_context() for skill in skills) or "No matching skill found."
    return f"Retrieved context:\n{_format_context(chunks)}\n\nRelevant skills:\n{skill_text}"


def _format_context(chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return "No memory retrieved."
    lines = []
    for chunk in chunks:
        path = str(chunk.get("path", "unknown.md"))
        heading = str(chunk.get("heading", "Document"))
        score = chunk.get("score", "")
        text = str(chunk.get("text", "")).strip()
        lines.append(f"[{path} :: {heading} :: score={score}]\n{text}")
    return "\n\n".join(lines)


def _answer_from_events(events: list[Any]) -> str:
    for event in reversed(events):
        if event.type == "session.done":
            return str(event.payload.get("result") or "").strip()
    return ""


def _actions_from_events(events: list[Any]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for event in events:
        if event.type == "tool.result":
            result = event.payload.get("result") or {}
            if isinstance(result, dict):
                actions.append(
                    {
                        "tool": result.get("tool"),
                        "args": result.get("input", {}),
                        "result": result.get("output"),
                        "ok": bool(result.get("success")),
                    }
                )
        elif event.type == "tool.error":
            result = event.payload.get("result") or {}
            if isinstance(result, dict):
                actions.append(
                    {
                        "tool": result.get("tool"),
                        "args": result.get("input", {}),
                        "error": result.get("error") or result.get("output"),
                        "ok": False,
                    }
                )
    return actions


def _answer_from_chunks(message: str, chunks: list[dict[str, object]], skills: list[object]) -> str:
    skill_text = "\n\nRelevant skills:\n" + "\n\n".join(skill.as_context() for skill in skills) if skills else ""
    if not chunks:
        return (
            "I could not find anything relevant in your workspace yet. "
            "Add a note or import a document and I will use it automatically."
            f"{skill_text}"
        )

    snippets = []
    seen = set()
    for chunk in chunks:
        path = str(chunk.get("path", "unknown.md"))
        text = str(chunk.get("text", "")).strip()
        key = (path, text)
        if key in seen:
            continue
        seen.add(key)
        preview = text[:220] + ("..." if len(text) > 220 else "")
        snippets.append(f"- {preview}")
    return f"I found relevant workspace context for your question: {message}\n\n" + "\n".join(snippets) + skill_text


__all__ = ["AgentLoop"]
