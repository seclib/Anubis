import json
import logging
from datetime import UTC, datetime
from typing import Any

from backend.agent.llm import LLM, OllamaLLM
from backend.agent.memory import MarkdownMemory
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import AgentTools
from backend.skills.parser import SkillRepository


logger = logging.getLogger("anubis.agent.loop")


class AgentLoop:
    def __init__(self, llm: LLM | None = None, max_iterations: int = 2) -> None:
        self.tools = AgentTools()
        self.memory = MarkdownMemory()
        self.skills = SkillRepository()
        self.llm = llm or OllamaLLM()
        self.max_iterations = max_iterations
        self.system_prompt = SYSTEM_PROMPT

    def chat(self, message: str) -> dict[str, object]:
        if message.lower().startswith("remember:"):
            target = self.memory.inject(message.split(":", 1)[1].strip())
            self.tools.reindex_memory()
            return {
                "answer": f"Knowledge stored in {target}.",
                "chunks_used": [],
                "skills_used": [],
                "actions": [{"tool": "write_note", "result": {"path": target}}],
                "memory_suggestion": None,
            }

        chunks = self.tools.rag_query(message)
        skills = self.skills.search(message)
        actions: list[dict[str, object]] = []
        answer = ""

        for _ in range(self.max_iterations):
            prompt = self._build_prompt(message, chunks, skills, actions)
            generated = self.llm.generate(prompt)
            answer, requested_actions = self._parse_llm_response(generated)
            if not requested_actions:
                break
            for action in requested_actions:
                result = self._execute_action(action)
                actions.append(result)
            if actions:
                chunks = self.tools.rag_query(message)

        if not answer:
            answer = self._answer_from_chunks(message, chunks, skills)

        memory_path = self._store_run(message, answer, chunks, skills, actions)

        return {
            "answer": answer,
            "chunks_used": chunks,
            "skills_used": [skill.as_context() for skill in skills],
            "actions": actions,
            "memory_path": memory_path,
            "memory_suggestion": self._memory_suggestion(message, chunks),
        }

    def _build_prompt(
        self,
        task: str,
        chunks: list[dict[str, object]],
        skills: list[object],
        actions: list[dict[str, object]],
    ) -> str:
        retrieved_context = self._format_context(chunks)
        retrieved_skills = "\n\n".join(skill.as_context() for skill in skills) or "No matching skill found."
        action_context = json.dumps(actions, indent=2) if actions else "No actions executed yet."
        return f"""{self.system_prompt}

Retrieved context:
{retrieved_context}

Retrieved skills:
{retrieved_skills}

Previous actions:
{action_context}

User task:
{task}
"""

    def _parse_llm_response(self, response: str) -> tuple[str, list[dict[str, Any]]]:
        text = response.strip()
        if not text:
            return "", []
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text, []
        if not isinstance(payload, dict):
            return text, []
        answer = str(payload.get("answer", "")).strip()
        raw_actions = payload.get("actions", [])
        actions = [action for action in raw_actions if isinstance(action, dict)] if isinstance(raw_actions, list) else []
        return answer, actions

    def _execute_action(self, action: dict[str, Any]) -> dict[str, object]:
        tool = str(action.get("tool", ""))
        args = action.get("args", {})
        if not isinstance(args, dict):
            args = {}
        try:
            result = self.tools.execute(tool, args)
            return {"tool": tool, "args": args, "result": result, "ok": True}
        except Exception as exc:
            logger.warning("agent action failed tool=%s error=%s", tool, exc)
            return {"tool": tool, "args": args, "error": str(exc), "ok": False}

    def _answer_from_chunks(self, message: str, chunks: list[dict[str, object]], skills: list[object]) -> str:
        skill_text = "\n\nRelevant skills:\n" + "\n\n".join(skill.as_context() for skill in skills) if skills else ""
        if not chunks:
            return (
                "I could not find anything relevant in your workspace yet. "
                "Add a note or import a document and I will use it automatically."
                f"{skill_text}"
            )

        snippets = self._format_snippets(chunks)
        return (
            "I found relevant workspace context for your question: "
            f"{message}\n\n{snippets}{skill_text}"
        )

    def _format_context(self, chunks: list[dict[str, object]]) -> str:
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

    def _format_snippets(self, chunks: list[dict[str, object]]) -> str:
        lines = []
        seen = set()
        for chunk in chunks:
            path = str(chunk.get("path", "unknown.md"))
            text = str(chunk.get("text", "")).strip()
            key = (path, text)
            if key in seen:
                continue
            seen.add(key)
            preview = text[:220] + ("..." if len(text) > 220 else "")
            lines.append(f"- {preview}")
        return "\n".join(lines)

    def _memory_suggestion(self, message: str, chunks: list[dict[str, object]]) -> str | None:
        if chunks:
            return None
        if len(message.strip()) < 40:
            return None
        return "This may be new information worth saving as a note."

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
