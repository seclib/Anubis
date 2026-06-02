from __future__ import annotations

import argparse
import asyncio
import json
import os
import readline
import re
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen


def _load_settings() -> Any:
    try:
        from backend.core.config import settings as backend_settings

        return backend_settings
    except Exception:
        return SimpleNamespace(
            vault_path=Path(os.getenv("ANUBIS_VAULT_PATH", "vault")),
            skills_path=Path(os.getenv("ANUBIS_SKILLS_PATH", "vault/skills")),
            project_root=Path(os.getenv("PROJECT_ROOT", ".")),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "anubis_chunks"),
            llm_model=os.getenv("ANUBIS_LLM_MODEL", "qwen2.5-coder:7b"),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            tool_timeout_seconds=int(os.getenv("ANUBIS_TOOL_TIMEOUT_SECONDS", "30")),
        )


settings = _load_settings()


class _UnavailableService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def search(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    def reindex_all(self) -> int:
        return 0

    def index_note(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def list_notes(self) -> list[dict[str, Any]]:
        return []

    def read_note(self, path: str) -> str:
        raise FileNotFoundError(path)

    def write_note(self, path: str, content: str) -> None:
        output = Path(settings.vault_path) / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")

    def execute(self, _request: Any) -> Any:
        return SimpleNamespace(ok=False, output="sandbox unavailable")


class _ToolRequest:
    def __init__(
        self,
        *,
        command: str,
        justification: str,
        cwd: str,
        allow_network: bool,
    ) -> None:
        self.command = command
        self.justification = justification
        self.cwd = cwd
        self.allow_network = allow_network


def _load_runtime_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from backend.rag.indexer import RagIndexer
        from backend.rag.retriever import RagRetriever
        from backend.skills.parser import SkillRepository
        from backend.tools.sandbox import SandboxExecutor, ToolRequest
        from backend.vault.service import VaultService

        return RagRetriever, RagIndexer, SkillRepository, VaultService, (SandboxExecutor, ToolRequest)
    except Exception:
        return (
            _UnavailableService,
            _UnavailableService,
            _UnavailableService,
            _UnavailableService,
            (_UnavailableService, _ToolRequest),
        )


HISTORY_FILE = Path("state/anubis_cli_history")
TRACE_DIR = "agent-runs"
MAX_CONTEXT_CHUNKS = 6
MAX_SKILLS = 4
LOW_CONFIDENCE_SCORE = 0.2
OBSIDIAN_FALLBACK_LIMIT = 8


@dataclass(frozen=True)
class AgentStep:
    id: int
    goal: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentPlan:
    task: str
    memory: list[dict[str, Any]]
    skills: list[Skill]
    steps: list[AgentStep]


@dataclass(frozen=True)
class StepResult:
    step: AgentStep
    ok: bool
    output: Any


@dataclass(frozen=True)
class Critique:
    accepted: bool
    retry: bool
    reason: str


class Terminal:
    def __init__(self, quiet: bool = False, debug: bool = False) -> None:
        self.quiet = quiet
        self.debug = debug

    def line(self, text: str = "") -> None:
        if not self.quiet:
            print(text)

    def status(self, text: str) -> None:
        if self.debug and not self.quiet:
            print(f"\033[2m{text}\033[0m")

    def error(self, text: str) -> None:
        print(f"\033[31m{text}\033[0m", file=sys.stderr)

    def token(self, text: str) -> None:
        print(text, end="", flush=True)


class StreamingOllama:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 120) -> None:
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            data = self._post_json("/api/chat", payload)
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return f"[LLM ERROR] {exc}"
        return str(data.get("message", {}).get("content") or data.get("response") or "").strip()

    def stream(self, prompt: str) -> Iterable[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {"temperature": 0.2},
        }
        try:
            body = json.dumps(payload).encode("utf-8")
            request = Request(
                f"{self.base_url}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except Exception:
            text = self.generate(prompt)
            if text:
                yield text

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


class AnubisAgent:
    def __init__(
        self,
        *,
        allow_tools: bool = False,
        max_rounds: int = 2,
        terminal: Terminal | None = None,
        llm: StreamingOllama | None = None,
    ) -> None:
        self.allow_tools = allow_tools
        self.max_rounds = max_rounds
        self.terminal = terminal or Terminal()
        self.llm = llm or StreamingOllama()
        RagRetriever, RagIndexer, SkillRepository, VaultService, sandbox_dependencies = _load_runtime_dependencies()
        SandboxExecutor, self._tool_request_type = sandbox_dependencies
        self.retriever = RagRetriever()
        self.indexer = RagIndexer()
        self.skills = SkillRepository()
        self.vault = VaultService()
        self.sandbox = SandboxExecutor()

    def ask(self, task: str, *, stream: bool = True) -> dict[str, Any]:
        started = time.time()
        feedback = ""
        history: list[dict[str, Any]] = []
        final_answer = ""

        for round_index in range(1, self.max_rounds + 1):
            self.terminal.status("memory: querying Qdrant")
            memory = self.retrieve_context(task)
            skills = self.retrieve_skills(task)

            self.terminal.status("planner: building execution plan")
            plan = self.plan(task, memory, skills, feedback)

            self.terminal.status("executor: running planned steps")
            results = self.execute(plan)

            final_answer = self.answer(task, plan, results, stream=False)
            self.terminal.status("critic: validating answer")
            critique = self.critique(task, plan, results, final_answer)
            history.append(
                {
                    "round": round_index,
                    "plan": self._plan_dict(plan),
                    "results": [self._result_dict(result) for result in results],
                    "critique": asdict(critique),
                    "answer": final_answer,
                }
            )

            if critique.accepted or not critique.retry:
                break
            feedback = critique.reason
            self.terminal.status(f"critic: retrying because {feedback}")

        if history and not history[-1]["critique"]["accepted"]:
            final_answer = f"I could not validate a grounded answer from retrieved memory. {history[-1]['critique']['reason']}"
            history[-1]["answer"] = final_answer

        if stream and final_answer:
            self.stream_text(final_answer)

        trace_path = self.store_trace(task, history, started)
        return {
            "task": task,
            "answer": final_answer,
            "accepted": history[-1]["critique"]["accepted"] if history else False,
            "trace": trace_path,
            "history": history,
        }

    def retrieve_memory(self, task: str) -> list[dict[str, Any]]:
        return self.retrieve_context(task)

    def retrieve_context(self, task: str) -> list[dict[str, Any]]:
        self.terminal.status("memory: querying Qdrant")
        qdrant_results = self.retrieve_qdrant(task)
        self.terminal.status("memory: querying Obsidian")
        obsidian_results = self.search_obsidian(task)
        self.terminal.status("memory: scoring sources")
        return self.score_and_route_context(task, qdrant_results, obsidian_results)

    def score_and_route_context(
        self,
        task: str,
        qdrant_results: list[dict[str, Any]],
        obsidian_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            from retrieval.memory_scoring import MemoryCandidate, route_memory
        except Exception:
            return self.merge_context(qdrant_results, obsidian_results)

        qdrant_candidates = [
            self._memory_candidate(item, source="qdrant", memory_candidate_type=MemoryCandidate)
            for item in qdrant_results
        ]
        obsidian_candidates = [
            self._memory_candidate(item, source="obsidian", memory_candidate_type=MemoryCandidate)
            for item in obsidian_results
        ]
        decision = route_memory(
            query=task,
            qdrant_candidates=qdrant_candidates,
            obsidian_candidates=obsidian_candidates,
            context_limit=MAX_CONTEXT_CHUNKS,
        )
        self.terminal.status(
            "memory: "
            f"{decision.selected_memory_source} "
            f"confidence={decision.confidence_score:.2f} "
            f"conflict={decision.conflict_flag}"
        )
        routed = [
            candidate.metadata["memory_item"]
            for candidate in decision.retrieved_context
            if isinstance(candidate.metadata.get("memory_item"), dict)
        ]
        if routed:
            return routed[:MAX_CONTEXT_CHUNKS]
        return self.merge_context(qdrant_results, obsidian_results)

    def retrieve_qdrant(self, task: str) -> list[dict[str, Any]]:
        try:
            results = self.retriever.search(task, MAX_CONTEXT_CHUNKS)
        except Exception as exc:
            self.terminal.status(f"memory: Qdrant unavailable ({exc})")
            return []
        return [self._normalize_memory_item(item, source="qdrant") for item in results]

    def search_obsidian(self, task: str) -> list[dict[str, Any]]:
        query_terms = self._terms(task)
        scored: list[tuple[float, dict[str, Any]]] = []

        for note in self.vault.list_notes():
            path = note.get("path", "")
            try:
                text = self.vault.read_note(path)
            except (OSError, ValueError):
                continue
            score = self._lexical_score(query_terms, text, path)
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "source": "obsidian",
                        "path": path,
                        "heading": note.get("title") or Path(path).stem,
                        "text": self._best_excerpt(text, query_terms),
                        "score": score,
                    },
                )
            )

        for skill in self.retrieve_skills(task):
            skill_text = skill.as_context()
            score = max(self._lexical_score(query_terms, skill_text, skill.path), 0.01)
            scored.append(
                (
                    score + 0.05,
                    {
                        "source": "obsidian_skill",
                        "path": skill.path,
                        "heading": f"skill: {skill.name}",
                        "text": skill_text,
                        "score": score + 0.05,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[:OBSIDIAN_FALLBACK_LIMIT]]

    def merge_context(self, qdrant_results: list[dict[str, Any]], obsidian_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in [*qdrant_results, *obsidian_results]:
            normalized = self._normalize_memory_item(item, source=str(item.get("source") or "memory"))
            key = (
                str(normalized.get("path", "")),
                str(normalized.get("heading", "")),
                str(normalized.get("text", ""))[:180],
            )
            existing = merged.get(key)
            if existing is None or float(normalized.get("score") or 0) > float(existing.get("score") or 0):
                merged[key] = normalized
        ranked = sorted(
            merged.values(),
            key=lambda item: (float(item.get("score") or 0), 1 if item.get("source") == "qdrant" else 0),
            reverse=True,
        )
        return ranked[:MAX_CONTEXT_CHUNKS]

    def retrieve_skills(self, task: str) -> list[Skill]:
        try:
            return self.skills.search(task, MAX_SKILLS)
        except Exception as exc:
            self.terminal.status(f"skills: unavailable ({exc})")
            return []

    def plan(self, task: str, memory: list[dict[str, Any]], skills: list[Skill], feedback: str = "") -> AgentPlan:
        prompt = {
            "role": "planner",
            "instruction": (
                "Create a compact plan for a terminal AI agent. Always use retrieved memory first. "
                "Only request shell tool use when absolutely required and safe."
            ),
            "tools_enabled": self.allow_tools,
            "task": task,
            "feedback": feedback,
            "memory": self._memory_for_prompt(memory),
            "skills": [skill.as_context() for skill in skills],
            "output_json": {"steps": [{"id": 1, "goal": "answer using memory", "tool": None, "args": {}}]},
        }
        raw = self.llm.generate(json.dumps(prompt, ensure_ascii=False))
        steps = self._parse_steps(raw)
        if not steps:
            steps = [AgentStep(id=1, goal="Answer using retrieved memory and matching skills")]
        return AgentPlan(task=task, memory=memory, skills=skills, steps=steps)

    def execute(self, plan: AgentPlan) -> list[StepResult]:
        results: list[StepResult] = []
        for step in plan.steps:
            if step.tool == "shell":
                if not self.allow_tools:
                    results.append(StepResult(step, False, "shell tools are disabled"))
                    continue
                request = self._tool_request_type(
                    command=str(step.args.get("command", "")),
                    justification=str(step.args.get("justification", step.goal)),
                    cwd=str(step.args.get("cwd", ".")),
                    allow_network=bool(step.args.get("allow_network", False)),
                )
                result = self.sandbox.execute(request)
                output = asdict(result) if hasattr(result, "__dataclass_fields__") else vars(result)
                results.append(StepResult(step, bool(getattr(result, "ok", False)), output))
                continue
            results.append(StepResult(step, True, {"status": "ready", "goal": step.goal}))
        return results

    def critique(self, task: str, plan: AgentPlan, results: list[StepResult], answer: str) -> Critique:
        if not plan.memory:
            return Critique(False, False, "Qdrant and Obsidian retrieval produced no relevant context")
        failed = [result for result in results if not result.ok]
        if failed:
            return Critique(False, self.allow_tools, f"{len(failed)} step(s) failed")
        if not answer.strip():
            return Critique(False, True, "answer was empty")
        prompt = {
            "role": "critic",
            "instruction": (
                "Validate the answer grounding. Accept only if factual claims are supported by retrieved memory, "
                "Obsidian truth is not overridden, Qdrant is used only as semantic support, and the answer addresses the task."
            ),
            "task": task,
            "answer": answer,
            "plan": self._plan_dict(plan),
            "results": [self._result_dict(result) for result in results],
            "output_json": {"accepted": True, "retry": False, "reason": "short reason"},
        }
        payload = self._json_object(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        if "accepted" in payload:
            accepted = bool(payload.get("accepted"))
            return Critique(
                accepted=accepted,
                retry=bool(payload.get("retry", not accepted)),
                reason=str(payload.get("reason", "")),
            )
        return Critique(True, False, "validated")

    def answer(self, task: str, plan: AgentPlan, results: list[StepResult], *, stream: bool) -> str:
        prompt = self._answer_prompt(task, plan, results)
        chunks: list[str] = []
        if stream:
            for token in self.llm.stream(prompt):
                chunks.append(token)
                self.terminal.token(token)
            self.terminal.line("\n")
        else:
            answer = self.llm.generate(prompt).strip()
            chunks.append(answer or self._fallback_answer(task, plan))
        answer = "".join(chunks).strip()
        return answer or self._fallback_answer(task, plan)

    def stream_text(self, text: str) -> None:
        for token in re.findall(r"\S+\s*", text):
            self.terminal.token(token)
        self.terminal.line("\n")

    def store_trace(self, task: str, history: list[dict[str, Any]], started: float) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = f"{TRACE_DIR}/{timestamp}-cli.md"
        answer = history[-1].get("answer", "") if history else ""
        content = "\n".join(
            [
                f"# Anubis CLI run {timestamp}",
                "",
                "## task",
                task.strip(),
                "",
                "## answer",
                str(answer).strip(),
                "",
                "## duration",
                f"{time.time() - started:.2f}s",
                "",
                "## trace",
                f"```json\n{json.dumps(history, indent=2, ensure_ascii=False, default=str)}\n```",
                "",
            ]
        )
        try:
            self.vault.write_note(path, content)
            self.indexer.index_note(path)
        except Exception as exc:
            self.terminal.status(f"trace: could not store run ({exc})")
        return path

    def sync(self) -> int:
        return self.indexer.reindex_all()

    def _answer_prompt(self, task: str, plan: AgentPlan, results: list[StepResult]) -> str:
        return json.dumps(
            {
                "role": "anubis_cli",
                "instruction": (
                    "Answer as a concise terminal AI agent using ONLY the retrieved memory and skills below. "
                    "Obsidian is the truth layer. Qdrant is the semantic expansion layer. "
                    "Do not rely on general LLM knowledge unless the retrieved context is insufficient; "
                    "if insufficient, say what is missing instead of guessing. Cite note paths when useful."
                ),
                "task": task,
                "memory": self._memory_for_prompt(plan.memory),
                "skills": [skill.as_context() for skill in plan.skills],
                "plan": [asdict(step) for step in plan.steps],
                "tool_results": [self._result_dict(result) for result in results],
            },
            ensure_ascii=False,
        )

    def _fallback_answer(self, task: str, plan: AgentPlan) -> str:
        if plan.memory:
            lines = [f"Relevant memory for: {task}", ""]
            for item in plan.memory[:4]:
                path = item.get("path", "memory")
                heading = item.get("heading", "Document")
                text = str(item.get("text", "")).strip().replace("\n", " ")
                lines.append(f"- {path} :: {heading}: {text[:320]}")
            return "\n".join(lines)
        return "I could not find relevant Obsidian/Qdrant memory for this yet. Add or sync notes, then ask again."

    def _needs_obsidian_fallback(self, results: list[dict[str, Any]]) -> bool:
        if not results:
            return True
        scores = [float(item.get("score") or 0) for item in results]
        return max(scores, default=0.0) < LOW_CONFIDENCE_SCORE or len(results) < 2

    def _normalize_memory_item(self, item: dict[str, Any], *, source: str) -> dict[str, Any]:
        return {
            "source": item.get("source") or source,
            "path": item.get("path") or "",
            "heading": item.get("heading") or "Document",
            "text": str(item.get("text") or "").strip(),
            "score": float(item.get("score") or 0),
            "hash": item.get("hash"),
        }

    def _memory_candidate(self, item: dict[str, Any], *, source: str, memory_candidate_type: Any) -> Any:
        normalized = self._normalize_memory_item(item, source=source)
        text = str(normalized.get("text") or "")
        path = str(normalized.get("path") or "")
        heading = str(normalized.get("heading") or Path(path).stem or "Memory")
        score = float(normalized.get("score") or 0.0)
        terms = tuple(sorted(self._terms(" ".join([path, heading, text]))))
        return memory_candidate_type(
            source="qdrant" if source == "qdrant" else "obsidian",
            content=text,
            qdrant_similarity=score if source == "qdrant" else 0.0,
            title=heading,
            tags=tuple(term for term in terms if term in {"skill", "memory", "truth", "workflow", "procedure"}),
            skills=terms if "skill" in str(normalized.get("source") or "") else (),
            keywords=terms,
            confidence=min(1.0, max(score, 0.65 if source == "obsidian" else 0.0)),
            metadata={"memory_item": normalized},
        )

    def _terms(self, query: str) -> set[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "for",
            "from",
            "how",
            "is",
            "it",
            "of",
            "on",
            "or",
            "the",
            "this",
            "to",
            "what",
            "why",
            "with",
        }
        cleaned = "".join(ch.lower() if ch.isalnum() or ch in {"_", "-"} else " " for ch in query)
        return {term for term in cleaned.split() if len(term) > 2 and term not in stopwords}

    def _lexical_score(self, query_terms: set[str], text: str, path: str = "") -> float:
        if not query_terms:
            return 0.0
        haystack = f"{path}\n{text}".lower()
        matches = sum(1 for term in query_terms if term in haystack)
        return matches / len(query_terms)

    def _best_excerpt(self, text: str, query_terms: set[str], limit: int = 1200) -> str:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return text.strip()[:limit]
        paragraphs.sort(key=lambda paragraph: self._lexical_score(query_terms, paragraph), reverse=True)
        selected: list[str] = []
        total = 0
        for paragraph in paragraphs[:4]:
            if total + len(paragraph) > limit:
                selected.append(paragraph[: max(0, limit - total)])
                break
            selected.append(paragraph)
            total += len(paragraph)
        return "\n\n".join(selected).strip()[:limit]

    def _parse_steps(self, raw: str) -> list[AgentStep]:
        payload = self._json_object(raw)
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            return []
        steps: list[AgentStep] = []
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal", "")).strip()
            if not goal:
                continue
            tool = item.get("tool")
            if tool and str(tool) != "shell":
                tool = None
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            steps.append(AgentStep(id=int(item.get("id", index)), goal=goal, tool=str(tool) if tool else None, args=args))
        return steps[:6]

    def _json_object(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _memory_for_prompt(self, memory: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact = []
        for item in memory[:MAX_CONTEXT_CHUNKS]:
            compact.append(
                {
                    "path": item.get("path"),
                    "heading": item.get("heading"),
                    "score": item.get("score"),
                    "text": str(item.get("text", ""))[:1200],
                }
            )
        return compact

    def _plan_dict(self, plan: AgentPlan) -> dict[str, Any]:
        return {
            "task": plan.task,
            "memory": self._memory_for_prompt(plan.memory),
            "skills": [skill.as_context() for skill in plan.skills],
            "steps": [asdict(step) for step in plan.steps],
        }

    def _result_dict(self, result: StepResult) -> dict[str, Any]:
        return {"step": asdict(result.step), "ok": result.ok, "output": result.output}


class AnubisCLI:
    def __init__(self, *, allow_tools: bool = False, quiet: bool = False, debug: bool = False) -> None:
        self.terminal = Terminal(quiet=quiet, debug=debug)
        self.agent = AnubisAgent(allow_tools=allow_tools, terminal=self.terminal)
        self.allow_tools = allow_tools

    async def repl(self) -> None:
        self._setup_history()
        self._banner()
        while True:
            try:
                user_input = input("\033[32mYou:\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                self.terminal.line("\nbye")
                break
            if not user_input:
                continue
            if user_input.startswith("/"):
                if not self.command(user_input):
                    break
                continue
            self.terminal.line("\033[36mAnubis:\033[0m")
            await self.run(user_input, stream=True)

    async def run(self, task: str, *, stream: bool = True) -> dict[str, Any]:
        if not task.strip():
            raise ValueError("task cannot be empty")
        self.terminal.line("\033[36mAnubis:\033[0m")
        return await asyncio.to_thread(self.agent.ask, task, stream=stream)

    async def orchestrate(self, task: str, *, stream: bool = True) -> dict[str, Any]:
        if not task.strip():
            raise ValueError("task cannot be empty")
        from runtime import AnubisOrchestrationEngine, event_to_dict

        self.terminal.line("\033[36mAnubis:\033[0m")
        engine = AnubisOrchestrationEngine()
        if not stream:
            result = await engine.run(task, stream=False)
            return {
                "answer": result.answer,
                "accepted": result.accepted,
                "events": [event_to_dict(event) for event in result.events],
            }

        async for event in engine.stream(task):
            if event.kind == "token":
                self.terminal.token(event.message + " ")
            elif event.stage != "output":
                self.terminal.status(f"{event.stage}: {event.message}")
        self.terminal.line("\n")
        return {"answer": "", "accepted": True, "events": []}

    def command(self, raw: str) -> bool:
        command, _, args = raw.partition(" ")
        command = command.lower()
        args = args.strip()
        if command in {"/q", "/quit", "/exit"}:
            self.terminal.line("bye")
            return False
        if command == "/help":
            self.terminal.line(
                textwrap.dedent(
                    """
                    /help              show commands
                    /sync              ingest Obsidian vault into Qdrant
                    /memory <query>    show retrieved memory
                    /skills <query>    show matching skills
                    /tools on|off      enable or disable sandboxed tool execution
                    /status            show runtime status
                    /clear             clear screen
                    /quit              exit
                    """
                ).strip()
            )
            return True
        if command == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            return True
        if command == "/sync":
            self.terminal.status("sync: indexing Obsidian vault")
            count = self.agent.sync()
            self.terminal.line(f"indexed {count} chunks")
            return True
        if command == "/memory":
            if not args:
                self.terminal.line("usage: /memory <query>")
                return True
            for item in self.agent.retrieve_memory(args):
                score = item.get("score", "")
                path = item.get("path", "")
                heading = item.get("heading", "")
                text = str(item.get("text", "")).strip().replace("\n", " ")
                self.terminal.line(f"- {score} {path} :: {heading}\n  {text[:300]}")
            return True
        if command == "/skills":
            query = args or "skill"
            for skill in self.agent.retrieve_skills(query):
                self.terminal.line(f"- {skill.name} ({skill.path})\n  {skill.when_to_use[:240]}")
            return True
        if command == "/tools":
            if args.lower() in {"on", "true", "yes"}:
                self.allow_tools = True
                self.agent.allow_tools = True
            elif args.lower() in {"off", "false", "no"}:
                self.allow_tools = False
                self.agent.allow_tools = False
            self.terminal.line(f"tools: {'on' if self.allow_tools else 'off'}")
            return True
        if command == "/status":
            self.terminal.line(f"model: {settings.llm_model}")
            self.terminal.line(f"ollama: {settings.ollama_url}")
            self.terminal.line(f"vault: {settings.vault_path}")
            self.terminal.line(f"qdrant: {settings.qdrant_url} / {settings.qdrant_collection}")
            self.terminal.line(f"tools: {'on' if self.allow_tools else 'off'}")
            return True
        self.terminal.line("unknown command; type /help")
        return True

    def _setup_history(self) -> None:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass
        import atexit

        atexit.register(readline.write_history_file, HISTORY_FILE)

    def _banner(self) -> None:
        self.terminal.line("Anubis CLI")
        self.terminal.line("Terminal-first autonomous agent. Type /help for commands, /quit to exit.\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anubis", description="Terminal-first Anubis AI agent")
    parser.add_argument("--tools", action="store_true", help="allow sandboxed tool execution")
    parser.add_argument("--debug", action="store_true", help="show retrieval, planner, executor, and critic status")
    parser.add_argument("--no-stream", action="store_true", help="disable token streaming")

    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser("run", help='run a single query, for example: anubis run "explain this repo"')
    run.add_argument("query", nargs="+", help="question or task for Anubis")
    run.add_argument("--no-stream", dest="run_no_stream", action="store_true", help="disable token streaming for this run")
    run.add_argument("--tools", dest="run_tools", action="store_true", help="allow sandboxed tool execution for this run")
    run.add_argument("--debug", dest="run_debug", action="store_true", help="show runtime status for this run")

    subcommands.add_parser("repl", help="start the interactive terminal loop")
    orchestrate = subcommands.add_parser("orchestrate", help="run the full Anubis OS orchestration engine")
    orchestrate.add_argument("query", nargs="+", help="question or task for Anubis")
    orchestrate.add_argument("--no-stream", dest="orchestrate_no_stream", action="store_true", help="disable token streaming for this orchestration run")
    orchestrate.add_argument("--debug", dest="orchestrate_debug", action="store_true", help="show orchestration stages")
    subcommands.add_parser("sync", help="sync Obsidian vault into Qdrant and exit")
    subcommands.add_parser("status", help="print runtime configuration and exit")

    parser.add_argument("task", nargs="*", help=argparse.SUPPRESS)
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    command = args.command
    tools = bool(getattr(args, "tools", False) or getattr(args, "run_tools", False))
    debug = bool(getattr(args, "debug", False) or getattr(args, "run_debug", False) or getattr(args, "orchestrate_debug", False))
    no_stream = bool(getattr(args, "no_stream", False) or getattr(args, "run_no_stream", False) or getattr(args, "orchestrate_no_stream", False))
    cli = AnubisCLI(allow_tools=tools, debug=debug)

    if command == "sync":
        count = await asyncio.to_thread(cli.agent.sync)
        print(f"indexed {count} chunks")
        return 0

    if command == "status":
        cli.command("/status")
        return 0

    if command == "run":
        result = await cli.run(" ".join(args.query), stream=not no_stream)
        if no_stream:
            print(result["answer"])
        return 0

    if command == "orchestrate":
        result = await cli.orchestrate(" ".join(args.query), stream=not no_stream)
        if no_stream:
            print(result["answer"])
        return 0

    if command == "repl":
        await cli.repl()
        return 0

    if args.task:
        result = await cli.run(" ".join(args.task), stream=not no_stream)
        if no_stream:
            print(result["answer"])
        return 0

    await cli.repl()
    return 0


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(asyncio.run(async_main(argv)))


if __name__ == "__main__":
    main()
