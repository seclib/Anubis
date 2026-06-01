from dataclasses import asdict, dataclass, field
import json
from typing import Any

from backend.agent.llm import LLM, OllamaLLM
from backend.agent.tools import AgentTools
from backend.tools.sandbox import SandboxExecutor, ToolRequest


@dataclass(frozen=True)
class Step:
    id: int
    goal: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    task: str
    context: list[dict[str, Any]]
    steps: list[Step]


@dataclass(frozen=True)
class StepResult:
    step: Step
    ok: bool
    output: Any


@dataclass(frozen=True)
class Critique:
    accepted: bool
    retry: bool
    reason: str


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
    def __init__(self, llm: LLM | None = None, tools: AgentTools | None = None) -> None:
        self.llm = llm or OllamaLLM()
        self.tools = tools or AgentTools()

    def plan(self, task: str, feedback: str = "") -> Plan:
        context = self.tools.search_rag(task)
        prompt = {
            "role": "planner",
            "task": task,
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
            steps = [Step(id=1, goal="Use retrieved memory to answer the task")]
        return Plan(task=task, context=context, steps=steps)

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
    def __init__(self, tools: AgentTools | None = None, sandbox: SandboxExecutor | None = None) -> None:
        self.tools = tools or AgentTools()
        self.sandbox = sandbox or SandboxExecutor()

    def execute(self, plan: Plan) -> list[StepResult]:
        return [self._execute_step(step) for step in plan.steps]

    def _execute_step(self, step: Step) -> StepResult:
        if step.tool == "shell":
            request = ToolRequest(
                command=str(step.args.get("command", "")),
                justification=str(step.args.get("justification", step.goal)),
                cwd=str(step.args.get("cwd", ".")),
                allow_network=bool(step.args.get("allow_network", False)),
            )
            result = self.sandbox.execute(request)
            return StepResult(step=step, ok=result.ok, output=asdict(result))
        if step.tool:
            try:
                output = self.tools.execute(step.tool, step.args)
                return StepResult(step=step, ok=True, output=output)
            except Exception as exc:
                return StepResult(step=step, ok=False, output=str(exc))
        return StepResult(step=step, ok=True, output={"note": step.goal})


class Critic:
    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or OllamaLLM()

    def critique(self, task: str, plan: Plan, results: list[StepResult]) -> Critique:
        failed = [result for result in results if not result.ok]
        if failed:
            return Critique(accepted=False, retry=True, reason=f"{len(failed)} step(s) failed")
        prompt = {
            "role": "critic",
            "task": task,
            "plan": self._plan_dict(plan),
            "results": [self._result_dict(result) for result in results],
            "output_contract": {"accepted": True, "retry": False, "reason": "..."},
        }
        payload = _json_from_llm(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        if "accepted" in payload:
            accepted = bool(payload.get("accepted"))
            return Critique(
                accepted=accepted,
                retry=bool(payload.get("retry", not accepted)),
                reason=str(payload.get("reason", "")),
            )
        return Critique(accepted=True, retry=False, reason="all steps completed")

    def _plan_dict(self, plan: Plan) -> dict[str, Any]:
        return {"task": plan.task, "context": plan.context, "steps": [asdict(step) for step in plan.steps]}

    def _result_dict(self, result: StepResult) -> dict[str, Any]:
        return {"step": asdict(result.step), "ok": result.ok, "output": result.output}


class MultiAgentLoop:
    def __init__(self, llm: LLM | None = None, max_rounds: int = 2) -> None:
        self.planner = Planner(llm=llm)
        self.executor = Executor()
        self.critic = Critic(llm=llm)
        self.max_rounds = max_rounds

    def run(self, task: str) -> dict[str, Any]:
        feedback = ""
        history = []
        for round_index in range(1, self.max_rounds + 1):
            plan = self.planner.plan(task, feedback=feedback)
            results = self.executor.execute(plan)
            critique = self.critic.critique(task, plan, results)
            history.append(
                {
                    "round": round_index,
                    "plan": {"task": plan.task, "context": plan.context, "steps": [asdict(step) for step in plan.steps]},
                    "results": [asdict(result) for result in results],
                    "critique": asdict(critique),
                }
            )
            if critique.accepted or not critique.retry:
                break
            feedback = critique.reason
        return {"task": task, "accepted": history[-1]["critique"]["accepted"], "history": history}


def run_task(task: str, max_rounds: int = 2) -> dict[str, Any]:
    return MultiAgentLoop(max_rounds=max_rounds).run(task)
