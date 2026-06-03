from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Protocol


class LLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class ToolRunner(Protocol):
    def search_rag(self, query: str) -> list[dict[str, Any]]:
        ...

    def execute(self, tool: str, args: dict[str, Any]) -> Any:
        ...


class SandboxRunner(Protocol):
    def execute(self, request: Any) -> Any:
        ...


@dataclass(frozen=True)
class Intent:
    label: str
    confidence: float
    requires_tools: bool = False


class NullLLM:
    def generate(self, prompt: str) -> str:
        return ""


class NullTools:
    def search_rag(self, query: str) -> list[dict[str, Any]]:
        return []

    def execute(self, tool: str, args: dict[str, Any]) -> Any:
        raise RuntimeError(f"tool unavailable: {tool}")


class ToolRequest:
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


def _default_llm() -> LLM:
    try:
        from backend.agent.llm import OllamaLLM

        return OllamaLLM()
    except Exception:
        return NullLLM()


def _default_tools() -> ToolRunner:
    try:
        from backend.agent.tools import AgentTools

        return AgentTools()
    except Exception:
        return NullTools()


def _default_sandbox() -> SandboxRunner:
    try:
        from backend.tools.sandbox import SandboxExecutor

        return SandboxExecutor()
    except Exception:
        return NullTools()


def _tool_request(
    *,
    command: str,
    justification: str,
    cwd: str,
    allow_network: bool,
) -> Any:
    try:
        from backend.tools.sandbox import ToolRequest as SandboxToolRequest

        return SandboxToolRequest(
            command=command,
            justification=justification,
            cwd=cwd,
            allow_network=allow_network,
        )
    except Exception:
        return ToolRequest(
            command=command,
            justification=justification,
            cwd=cwd,
            allow_network=allow_network,
        )


@dataclass(frozen=True)
class Step:
    id: int
    goal: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    task: str
    intent: Intent
    context: list[dict[str, Any]]
    steps: list[Step]


@dataclass(frozen=True)
class StepResult:
    step: Step
    ok: bool
    output: Any
    error: str = ""


@dataclass(frozen=True)
class ExecutorOutput:
    draft_response: str
    citations: list[str]
    step_results: list[StepResult]
    structured: bool = True


@dataclass(frozen=True)
class Critique:
    accepted: bool
    retry: bool
    reason: str
    hallucination_risk: float = 1.0
    grounding_score: float = 0.0


class IntentClassifier:
    KEYWORDS = {
        "implementation": ("build", "code", "create", "edit", "fix", "implement", "refactor"),
        "debugging": ("bug", "error", "fail", "regression", "test", "traceback"),
        "research": ("explain", "find", "summarize", "what", "why"),
        "security": ("attack", "audit", "inject", "malware", "policy", "sandbox", "security", "threat"),
        "memory": ("memory", "note", "obsidian", "qdrant", "recall", "retrieve"),
    }

    def classify(self, query: str) -> Intent:
        text = query.lower()
        scores = {
            label: sum(1 for keyword in keywords if keyword in text)
            for label, keywords in self.KEYWORDS.items()
        }
        label, score = max(scores.items(), key=lambda item: item[1])
        if score <= 0:
            return Intent("general", 0.35, False)
        return Intent(label, min(1.0, 0.45 + score * 0.15), label in {"implementation", "debugging", "security"})


def _json_from_llm(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class Planner:
    def __init__(self, llm: LLM | None = None, tools: ToolRunner | None = None) -> None:
        self.llm = llm or _default_llm()
        self.tools = tools or _default_tools()

    def plan(self, task: str, feedback: str = "", intent: Intent | None = None) -> Plan:
        intent = intent or IntentClassifier().classify(task)
        context = self._retrieve_context(task, feedback, intent)
        prompt = {
            "role": "planner",
            "rules": [
                "Return JSON only.",
                "Retrieval has already happened; never plan from memory-free assumptions.",
                "Decompose the task before any answer is attempted.",
                "Every step must be executable and grounded in retrieved_context.",
                "Treat Obsidian entries as the truth layer and Qdrant entries as recall hints.",
            ],
            "task": task,
            "intent": asdict(intent),
            "feedback": feedback,
            "retrieved_context": context,
            "output_contract": {
                "steps": [
                    {"id": 1, "goal": "short step", "tool": None, "args": {}}
                ]
            },
        }
        payload = _json_from_llm(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        steps = self._steps(payload.get("steps"))
        if not steps:
            steps = [
                Step(id=1, goal="Inspect Obsidian truth notes and relevant recall chunks"),
                Step(id=2, goal="Draft a response using only retrieved evidence"),
                Step(id=3, goal="List citations for every factual claim"),
            ]
        return Plan(task=task, intent=intent, context=context, steps=steps)

    def _retrieve_context(self, task: str, feedback: str, intent: Intent) -> list[dict[str, Any]]:
        query = f"{task}\n{feedback}".strip() if feedback else task
        if intent.label not in {"general", "research"}:
            query = f"{query}\nintent:{intent.label}"
        try:
            return _normalize_memory(self.tools.search_rag(query))
        except Exception:
            return []

    def _steps(self, raw: Any) -> list[Step]:
        if not isinstance(raw, list):
            return []
        steps = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal", "")).strip()
            if not goal:
                continue
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            tool = item.get("tool")
            steps.append(Step(id=int(item.get("id", index)), goal=goal, tool=str(tool) if tool else None, args=args))
        return steps


class Executor:
    def __init__(
        self,
        llm: LLM | None = None,
        tools: ToolRunner | None = None,
        sandbox: SandboxRunner | None = None,
    ) -> None:
        self.llm = llm or _default_llm()
        self.tools = tools or _default_tools()
        self.sandbox = sandbox or _default_sandbox()

    def execute(self, plan: Plan) -> ExecutorOutput:
        if not plan.steps:
            return ExecutorOutput(
                draft_response="",
                citations=[],
                step_results=[],
                structured=True,
            )
        results = [self._execute_step(step, plan) for step in plan.steps]
        draft, citations, structured = self._draft_response(plan, results)
        return ExecutorOutput(
            draft_response=draft,
            citations=citations,
            step_results=results,
            structured=structured,
        )

    def _execute_step(self, step: Step, plan: Plan) -> StepResult:
        if step.tool == "shell":
            request = _tool_request(
                command=str(step.args.get("command", "")),
                justification=str(step.args.get("justification", step.goal)),
                cwd=str(step.args.get("cwd", ".")),
                allow_network=bool(step.args.get("allow_network", False)),
            )
            result = self.sandbox.execute(request)
            output = asdict(result) if hasattr(result, "__dataclass_fields__") else vars(result)
            return StepResult(step=step, ok=bool(getattr(result, "ok", False)), output=output)
        if step.tool:
            try:
                output = self.tools.execute(step.tool, step.args)
                return StepResult(step=step, ok=True, output=output)
            except Exception as exc:
                return StepResult(step=step, ok=False, output={}, error=str(exc))
        return StepResult(step=step, ok=True, output={"evidence": self._evidence_for_step(step, plan)})

    def _draft_response(self, plan: Plan, results: list[StepResult]) -> tuple[str, list[str], bool]:
        prompt = {
            "role": "executor",
            "rules": [
                "Return JSON only.",
                "Use the plan and step_results.",
                "Do not add facts that are absent from retrieved_context.",
                "Cite source paths from retrieved_context.",
                "Prefer Obsidian facts over Qdrant recall when they conflict.",
            ],
            "task": plan.task,
            "intent": asdict(plan.intent),
            "retrieved_context": plan.context,
            "plan": [asdict(step) for step in plan.steps],
            "step_results": [asdict(result) for result in results],
            "output_contract": {"answer": "grounded final draft", "citations": ["path-or-source"]},
        }
        payload = _json_from_llm(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        answer = str(payload.get("answer") or "").strip()
        raw_citations = payload.get("citations")
        citations = [str(item) for item in raw_citations if item] if isinstance(raw_citations, list) else []
        if answer:
            return answer, citations, True
        return self._fallback_answer(plan), self._fallback_citations(plan), True

    def _evidence_for_step(self, step: Step, plan: Plan) -> list[dict[str, Any]]:
        terms = _terms(f"{plan.task} {step.goal}")
        ranked = sorted(
            plan.context,
            key=lambda chunk: (_overlap(terms, _terms(_chunk_text(chunk))), float(chunk.get("score") or 0.0)),
            reverse=True,
        )
        return ranked[:3]

    def _fallback_answer(self, plan: Plan) -> str:
        snippets = []
        for chunk in plan.context[:4]:
            path = chunk.get("path") or chunk.get("source") or "memory"
            text = _chunk_text(chunk).strip()
            if text:
                snippets.append(f"[{path}] {text[:700]}")
        return "\n\n".join(snippets)

    def _fallback_citations(self, plan: Plan) -> list[str]:
        citations = []
        for chunk in plan.context[:4]:
            citation = str(chunk.get("path") or chunk.get("source") or "").strip()
            if citation and citation not in citations:
                citations.append(citation)
        return citations


class Critic:
    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or _default_llm()

    def critique(self, task: str, plan: Plan, output: ExecutorOutput) -> Critique:
        if not plan.steps:
            return Critique(False, True, "planner produced no executable steps", 1.0, 0.0)
        if not plan.context:
            return Critique(
                accepted=False,
                retry=False,
                reason="no relevant memory was retrieved before execution",
                hallucination_risk=1.0,
                grounding_score=0.0,
            )
        if not _has_truth_source(plan.context):
            return Critique(
                accepted=False,
                retry=True,
                reason="retrieved context lacks Obsidian truth-layer grounding",
                hallucination_risk=0.95,
                grounding_score=0.0,
            )
        if not output.structured:
            return Critique(False, True, "executor output was not structured JSON", 1.0, 0.0)
        failed = [result for result in output.step_results if not result.ok]
        if failed:
            return Critique(False, True, f"{len(failed)} step(s) failed", 0.8, 0.0)
        if not output.draft_response.strip():
            return Critique(False, True, "executor returned no grounded draft", 1.0, 0.0)
        grounding = _grounding_score(output.draft_response, plan.context)
        hallucination = round(1.0 - grounding, 6)
        if grounding < 0.12:
            return Critique(False, True, "draft is weakly grounded in retrieved context", hallucination, grounding)
        prompt = {
            "role": "critic",
            "rules": [
                "Return JSON only.",
                "Reject unsupported claims.",
                "Set retry true when the executor should revise.",
                "Never approve if there was no plan or no retrieved context.",
                "Never approve if the answer is not grounded by Obsidian truth-layer memory.",
            ],
            "task": task,
            "plan": self._plan_dict(plan),
            "executor_output": self._executor_dict(output),
            "metrics": {"grounding_score": grounding, "hallucination_risk": hallucination},
            "output_contract": {
                "accepted": True,
                "retry": False,
                "reason": "short reason",
                "final_answer": "optional edited answer",
            },
        }
        payload = _json_from_llm(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        if "accepted" in payload:
            accepted = bool(payload.get("accepted"))
            return Critique(
                accepted=accepted,
                retry=bool(payload.get("retry", not accepted)),
                reason=str(payload.get("reason", "")),
                hallucination_risk=hallucination,
                grounding_score=grounding,
            )
        return Critique(True, False, "grounding accepted", hallucination, grounding)

    def _plan_dict(self, plan: Plan) -> dict[str, Any]:
        return {"task": plan.task, "context": plan.context, "steps": [asdict(step) for step in plan.steps]}

    def _result_dict(self, result: StepResult) -> dict[str, Any]:
        return {"step": asdict(result.step), "ok": result.ok, "output": result.output}

    def _executor_dict(self, output: ExecutorOutput) -> dict[str, Any]:
        return {
            "draft_response": output.draft_response,
            "citations": output.citations,
            "step_results": [self._result_dict(result) for result in output.step_results],
            "structured": output.structured,
        }


class MultiAgentLoop:
    def __init__(
        self,
        llm: LLM | None = None,
        tools: ToolRunner | None = None,
        sandbox: SandboxRunner | None = None,
        max_rounds: int = 2,
    ) -> None:
        self.planner = Planner(llm=llm, tools=tools)
        self.executor = Executor(llm=llm, tools=tools, sandbox=sandbox)
        self.critic = Critic(llm=llm)
        self.classifier = IntentClassifier()
        self.max_rounds = max_rounds

    def run(self, task: str) -> dict[str, Any]:
        intent = self.classifier.classify(task)
        feedback = ""
        history = []
        final_answer = ""
        final_critique: Critique | None = None
        for round_index in range(1, self.max_rounds + 1):
            plan = self.planner.plan(task, feedback=feedback, intent=intent)
            output = self.executor.execute(plan)
            critique = self.critic.critique(task, plan, output)
            final_critique = critique
            history.append(
                {
                    "round": round_index,
                    "intent": asdict(intent),
                    "plan": {
                        "task": plan.task,
                        "intent": asdict(plan.intent),
                        "context": plan.context,
                        "steps": [asdict(step) for step in plan.steps],
                    },
                    "executor_output": asdict(output),
                    "critique": asdict(critique),
                }
            )
            if critique.accepted:
                final_answer = output.draft_response
                break
            if not critique.retry:
                break
            feedback = critique.reason
        return {
            "task": task,
            "answer": final_answer,
            "accepted": bool(final_critique and final_critique.accepted),
            "history": history,
            "final_critique": asdict(final_critique) if final_critique else None,
        }


def _chunk_text(chunk: dict[str, Any]) -> str:
    return str(chunk.get("text") or chunk.get("content") or chunk.get("markdown") or "")


def _chunk_source(chunk: dict[str, Any]) -> str:
    return str(chunk.get("source") or chunk.get("backend") or chunk.get("kind") or chunk.get("path") or "").lower()


def _has_truth_source(context: list[dict[str, Any]]) -> bool:
    for chunk in context:
        source = _chunk_source(chunk)
        if "obsidian" in source or str(chunk.get("path") or "").endswith(".md"):
            return True
    return False


def _normalize_memory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _chunk_text(row).strip()
        if not text:
            continue
        source = row.get("source") or row.get("backend") or row.get("kind")
        path = row.get("path") or row.get("title") or row.get("id") or ""
        normalized.append(
            {
                **row,
                "text": text,
                "path": str(path),
                "source": str(source or ("obsidian" if str(path).endswith(".md") else "qdrant")),
                "score": float(row.get("score") or 0.0),
            }
        )
    normalized.sort(
        key=lambda chunk: (
            1 if "obsidian" in _chunk_source(chunk) or str(chunk.get("path") or "").endswith(".md") else 0,
            float(chunk.get("score") or 0.0),
        ),
        reverse=True,
    )
    return normalized


def _terms(text: str) -> set[str]:
    stopwords = {"and", "are", "but", "for", "from", "not", "that", "the", "this", "with", "your"}
    return {term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()) if term not in stopwords}


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _grounding_score(draft: str, context: list[dict[str, Any]]) -> float:
    context_terms: set[str] = set()
    for chunk in context:
        context_terms |= _terms(_chunk_text(chunk))
    return round(_overlap(_terms(draft), context_terms), 6)


def run_task(task: str, max_rounds: int = 2) -> dict[str, Any]:
    return MultiAgentLoop(max_rounds=max_rounds).run(task)
