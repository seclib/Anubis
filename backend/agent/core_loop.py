from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import re
from typing import Any, Protocol


class LLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class MemoryRetriever(Protocol):
    def retrieve(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        ...


class ToolExecutor(Protocol):
    def execute(self, tool: str, args: dict[str, Any]) -> Any:
        ...


@dataclass(frozen=True)
class MemoryItem:
    source: str
    text: str
    score: float = 0.0
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Intent:
    label: str
    confidence: float
    requires_tools: bool = False


@dataclass(frozen=True)
class PlanStep:
    id: int
    goal: str
    kind: str = "reason"
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    query: str
    intent: Intent
    memory: tuple[MemoryItem, ...]
    steps: tuple[PlanStep, ...]
    retry_feedback: str = ""


@dataclass(frozen=True)
class StepResult:
    step_id: int
    ok: bool
    output: str
    tool: str | None = None
    error: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    draft: str
    steps: tuple[StepResult, ...]


@dataclass(frozen=True)
class Critique:
    accepted: bool
    retry: bool
    hallucination_risk: float
    grounding_score: float
    reason: str


@dataclass(frozen=True)
class AgentRun:
    query: str
    answer: str
    accepted: bool
    rounds: tuple[dict[str, Any], ...]
    memory_used: tuple[MemoryItem, ...]
    final_critique: Critique


class DeterministicLLM:
    def generate(self, prompt: str) -> str:
        return ""


class NullToolExecutor:
    def execute(self, tool: str, args: dict[str, Any]) -> Any:
        raise RuntimeError(f"tool unavailable: {tool}")


class CompositeMemoryRetriever:
    def __init__(self, obsidian: MemoryRetriever | None = None, qdrant: MemoryRetriever | None = None) -> None:
        self.obsidian = obsidian
        self.qdrant = qdrant

    def retrieve(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for retriever in (self.obsidian, self.qdrant):
            if retriever is not None:
                rows.extend(retriever.retrieve(query, limit=limit))
        rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return rows[:limit]


class IntentClassifier:
    KEYWORDS = {
        "debugging": ("bug", "traceback", "error", "failing", "regression", "test"),
        "cybersecurity": ("incident", "alert", "threat", "log", "anomaly", "malware", "privilege"),
        "rag": ("retrieve", "memory", "qdrant", "obsidian", "ground", "citation"),
        "implementation": ("build", "implement", "refactor", "change", "code", "feature"),
    }

    def classify(self, query: str) -> Intent:
        text = query.lower()
        scored = {
            label: sum(1 for word in words if word in text)
            for label, words in self.KEYWORDS.items()
        }
        label, score = max(scored.items(), key=lambda item: item[1])
        if score <= 0:
            return Intent("general", 0.35, requires_tools=False)
        return Intent(label, min(1.0, 0.45 + score * 0.15), requires_tools=label in {"debugging", "implementation"})


class Planner:
    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or DeterministicLLM()

    def plan(self, query: str, intent: Intent, memory: tuple[MemoryItem, ...], retry_feedback: str = "") -> Plan:
        if not memory:
            return Plan(query, intent, memory, (), retry_feedback)
        prompt = {
            "role": "planner",
            "rule": "Plan only from retrieved memory. Do not invent facts.",
            "query": query,
            "intent": asdict(intent),
            "memory": [asdict(item) for item in memory],
            "retry_feedback": retry_feedback,
            "schema": {"steps": [{"id": 1, "goal": "grounded step", "kind": "reason", "tool": None, "args": {}}]},
        }
        payload = parse_json(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        steps = self._steps(payload.get("steps"))
        if not steps:
            steps = (
                PlanStep(1, "Identify relevant retrieved evidence", "reason"),
                PlanStep(2, "Synthesize an answer only from retrieved evidence", "reason"),
                PlanStep(3, "Check for unsupported claims before finalizing", "reason"),
            )
        return Plan(query, intent, memory, steps, retry_feedback)

    def _steps(self, raw: Any) -> tuple[PlanStep, ...]:
        if not isinstance(raw, list):
            return ()
        steps: list[PlanStep] = []
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal") or "").strip()
            if not goal:
                continue
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            tool = item.get("tool")
            steps.append(PlanStep(int(item.get("id") or index), goal, str(item.get("kind") or "reason"), str(tool) if tool else None, args))
        return tuple(steps)


class Executor:
    def __init__(self, llm: LLM | None = None, tools: ToolExecutor | None = None) -> None:
        self.llm = llm or DeterministicLLM()
        self.tools = tools or NullToolExecutor()

    def execute(self, plan: Plan) -> ExecutionResult:
        if not plan.memory:
            return ExecutionResult("", (StepResult(0, False, "", error="retrieval required before execution"),))
        results = tuple(self._step(step, plan) for step in plan.steps)
        draft = self._draft(plan, results)
        return ExecutionResult(draft, results)

    def _step(self, step: PlanStep, plan: Plan) -> StepResult:
        if step.tool:
            try:
                output = self.tools.execute(step.tool, step.args)
                return StepResult(step.id, True, stringify(output), step.tool)
            except Exception as exc:
                return StepResult(step.id, False, "", step.tool, str(exc))
        evidence = best_evidence(plan.memory, plan.query, limit=3)
        return StepResult(step.id, True, "\n".join(item.text[:700] for item in evidence))

    def _draft(self, plan: Plan, results: tuple[StepResult, ...]) -> str:
        prompt = {
            "role": "executor",
            "rule": "Answer only from retrieved memory and step results. Cite memory paths when available.",
            "query": plan.query,
            "memory": [asdict(item) for item in plan.memory],
            "steps": [asdict(item) for item in results],
        }
        generated = self.llm.generate(json.dumps(prompt, ensure_ascii=False)).strip()
        if generated:
            return generated
        lines = ["Grounded answer from retrieved memory:"]
        for item in best_evidence(plan.memory, plan.query, limit=4):
            source = item.path or item.source
            lines.append(f"- [{source}] {item.text[:500].strip()}")
        return "\n".join(lines)


class Critic:
    def __init__(self, llm: LLM | None = None, min_grounding: float = 0.35, max_hallucination: float = 0.45) -> None:
        self.llm = llm or DeterministicLLM()
        self.min_grounding = min_grounding
        self.max_hallucination = max_hallucination

    def critique(self, plan: Plan, result: ExecutionResult) -> Critique:
        if not plan.memory:
            return Critique(False, False, 1.0, 0.0, "no retrieved memory; answer blocked")
        if any(not step.ok for step in result.steps):
            return Critique(False, True, 0.8, 0.0, "one or more execution steps failed")
        grounding = grounding_score(result.draft, plan.memory)
        hallucination = hallucination_risk(result.draft, plan.memory)
        if grounding < self.min_grounding:
            return Critique(False, True, hallucination, grounding, "draft is weakly grounded in retrieved memory")
        if hallucination > self.max_hallucination:
            return Critique(False, True, hallucination, grounding, "hallucination risk exceeds threshold")
        llm_review = self._llm_review(plan, result, grounding, hallucination)
        if llm_review is not None:
            return llm_review
        return Critique(True, False, hallucination, grounding, "grounding accepted")

    def _llm_review(self, plan: Plan, result: ExecutionResult, grounding: float, hallucination: float) -> Critique | None:
        prompt = {
            "role": "critic",
            "rule": "Validate grounding. Reject unsupported claims.",
            "query": plan.query,
            "draft": result.draft,
            "memory": [asdict(item) for item in plan.memory],
            "metrics": {"grounding": grounding, "hallucination_risk": hallucination},
            "schema": {"accepted": True, "retry": False, "reason": "short reason"},
        }
        payload = parse_json(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        if "accepted" not in payload:
            return None
        accepted = bool(payload.get("accepted"))
        return Critique(accepted, bool(payload.get("retry", not accepted)), hallucination, grounding, str(payload.get("reason") or "critic reviewed"))


class AgentLoop:
    def __init__(
        self,
        memory: MemoryRetriever,
        llm: LLM | None = None,
        tools: ToolExecutor | None = None,
        max_rounds: int = 3,
        retrieval_limit: int = 8,
    ) -> None:
        self.memory = memory
        self.classifier = IntentClassifier()
        self.planner = Planner(llm)
        self.executor = Executor(llm, tools)
        self.critic = Critic(llm)
        self.max_rounds = max_rounds
        self.retrieval_limit = retrieval_limit

    def run(self, query: str) -> AgentRun:
        intent = self.classifier.classify(query)
        memory = tuple(to_memory_item(item) for item in self.memory.retrieve(query, self.retrieval_limit))
        if not memory:
            critique = Critique(False, False, 1.0, 0.0, "no memory retrieved; no answer generated")
            return AgentRun(query, "", False, (), (), critique)
        rounds: list[dict[str, Any]] = []
        feedback = ""
        final_result = ExecutionResult("", ())
        final_critique = Critique(False, True, 1.0, 0.0, "not started")
        for round_index in range(1, self.max_rounds + 1):
            plan = self.planner.plan(query, intent, memory, feedback)
            final_result = self.executor.execute(plan)
            final_critique = self.critic.critique(plan, final_result)
            rounds.append(
                {
                    "round": round_index,
                    "plan": serialize_plan(plan),
                    "execution": asdict(final_result),
                    "critique": asdict(final_critique),
                }
            )
            if final_critique.accepted or not final_critique.retry:
                break
            feedback = final_critique.reason
            memory = tuple(to_memory_item(item) for item in self.memory.retrieve(f"{query}\n{feedback}", self.retrieval_limit))
            if not memory:
                final_critique = Critique(False, False, 1.0, 0.0, "retry retrieval returned no memory")
                break
        answer = final_result.draft if final_critique.accepted else ""
        return AgentRun(query, answer, final_critique.accepted, tuple(rounds), memory, final_critique)


def to_memory_item(raw: Mapping[str, Any]) -> MemoryItem:
    text = str(raw.get("text") or raw.get("content") or raw.get("markdown") or "").strip()
    return MemoryItem(
        source=str(raw.get("source") or raw.get("backend") or raw.get("kind") or "memory"),
        text=text,
        score=float(raw.get("score") or 0.0),
        path=str(raw.get("path") or raw.get("title") or ""),
        metadata=dict(raw.get("metadata") or raw.get("payload") or {}),
    )


def best_evidence(memory: tuple[MemoryItem, ...], query: str, limit: int) -> tuple[MemoryItem, ...]:
    terms = key_terms(query)
    scored = sorted(memory, key=lambda item: (overlap(terms, key_terms(item.text)), item.score), reverse=True)
    return tuple(item for item in scored if item.text)[:limit]


def grounding_score(draft: str, memory: tuple[MemoryItem, ...]) -> float:
    draft_terms = key_terms(draft)
    memory_terms = set().union(*(key_terms(item.text) for item in memory)) if memory else set()
    return round(overlap(draft_terms, memory_terms), 6)


def hallucination_risk(draft: str, memory: tuple[MemoryItem, ...]) -> float:
    if not draft.strip():
        return 1.0
    return round(1.0 - grounding_score(draft, memory), 6)


def key_terms(text: str) -> set[str]:
    stop = {"and", "are", "but", "for", "from", "not", "that", "the", "this", "with", "your"}
    return {word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()) if word not in stop}


def overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def serialize_plan(plan: Plan) -> dict[str, Any]:
    return {
        "query": plan.query,
        "intent": asdict(plan.intent),
        "memory": [asdict(item) for item in plan.memory],
        "steps": [asdict(item) for item in plan.steps],
        "retry_feedback": plan.retry_feedback,
    }


def run_agent(query: str, memory: MemoryRetriever, max_rounds: int = 3) -> dict[str, Any]:
    run = AgentLoop(memory=memory, max_rounds=max_rounds).run(query)
    return {
        "query": run.query,
        "answer": run.answer,
        "accepted": run.accepted,
        "rounds": run.rounds,
        "memory_used": [asdict(item) for item in run.memory_used],
        "final_critique": asdict(run.final_critique),
        "completed_at": datetime.now(UTC).isoformat(),
    }
