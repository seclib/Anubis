from __future__ import annotations

import argparse
import json
import os
import readline
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import requests

from backend.agent.llm import OllamaLLM
from backend.core.config import settings
from backend.rag.indexer import RagIndexer
from backend.rag.retriever import RagRetriever
from backend.skills.parser import Skill, SkillRepository
from backend.tools.sandbox import SandboxExecutor, ToolRequest
from backend.vault.service import VaultService


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
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    def line(self, text: str = "") -> None:
        if not self.quiet:
            print(text)

    def status(self, text: str) -> None:
        if not self.quiet:
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
        self.fallback = OllamaLLM(model=self.model, base_url=self.base_url, timeout=timeout)

    def generate(self, prompt: str) -> str:
        return self.fallback.generate(prompt)

    def stream(self, prompt: str) -> Iterable[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {"temperature": 0.2},
        }
        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
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

            self.terminal.status("critic: validating answer")
            critique = self.critique(task, plan, results)

            final_answer = self.answer(task, plan, results, stream=stream)
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
        qdrant_results = self.retrieve_qdrant(task)
        obsidian_results: list[dict[str, Any]] = []
        if self._needs_obsidian_fallback(qdrant_results):
            self.terminal.status("memory: Qdrant context insufficient; searching Obsidian fallback")
            obsidian_results = self.search_obsidian(task)
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
                request = ToolRequest(
                    command=str(step.args.get("command", "")),
                    justification=str(step.args.get("justification", step.goal)),
                    cwd=str(step.args.get("cwd", ".")),
                    allow_network=bool(step.args.get("allow_network", False)),
                )
                result = self.sandbox.execute(request)
                results.append(StepResult(step, result.ok, asdict(result)))
                continue
            results.append(StepResult(step, True, {"status": "ready", "goal": step.goal}))
        return results

    def critique(self, task: str, plan: AgentPlan, results: list[StepResult]) -> Critique:
        if not plan.memory:
            return Critique(False, False, "Qdrant and Obsidian retrieval produced no relevant context")
        failed = [result for result in results if not result.ok]
        if failed:
            return Critique(False, self.allow_tools, f"{len(failed)} step(s) failed")
        prompt = {
            "role": "critic",
            "instruction": "Validate whether the agent has enough context and successful steps to answer.",
            "task": task,
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
                    "Qdrant memory is primary. Obsidian fallback memory is secondary. "
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
    def __init__(self, *, allow_tools: bool = False, quiet: bool = False) -> None:
        self.terminal = Terminal(quiet=quiet)
        self.agent = AnubisAgent(allow_tools=allow_tools, terminal=self.terminal)
        self.allow_tools = allow_tools

    def repl(self) -> None:
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
            self.agent.ask(user_input, stream=True)

    def once(self, task: str) -> None:
        self.terminal.line("\033[36mAnubis:\033[0m")
        self.agent.ask(task, stream=True)

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
    parser.add_argument("task", nargs="*", help="single-shot question or task")
    parser.add_argument("--tools", action="store_true", help="allow sandboxed tool execution")
    parser.add_argument("--sync", action="store_true", help="sync Obsidian vault into Qdrant and exit")
    parser.add_argument("--no-stream", action="store_true", help="disable token streaming")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cli = AnubisCLI(allow_tools=args.tools)
    if args.sync:
        count = cli.agent.sync()
        print(f"indexed {count} chunks")
        return
    if args.task:
        task_parts = args.task[1:] if args.task[0] == "run" else args.task
        task = " ".join(task_parts)
        if not task:
            raise SystemExit('usage: anubis run "<query>"')
        if args.no_stream:
            result = cli.agent.ask(task, stream=False)
            print(result["answer"])
            return
        cli.once(task)
        return
    cli.repl()


if __name__ == "__main__":
    main()
