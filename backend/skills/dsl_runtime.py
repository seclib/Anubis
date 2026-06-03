from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any, Callable, Mapping


ALLOWED_ACTIONS = {"SEARCH_MEMORY", "QUERY_QDRANT", "CALL_LLM", "RUN_TOOL", "IF", "THEN", "RETURN"}
DEFAULT_ALLOWED_TOOLS = {"search_memory", "query_qdrant", "summarize", "classify", "format_report"}
FORBIDDEN_TOOL_ARG_KEYS = {"code", "command", "shell", "python", "eval", "exec", "subprocess", "__import__"}
FORBIDDEN_TOOL_ARG_TEXT = re.compile(
    r"(?i)(rm\s+-rf|sudo|curl\s+.*\|\s*sh|wget\s+.*\|\s*sh|bash\s+-c|sh\s+-c|python\s+-c|eval\(|exec\(|__import__|subprocess)"
)
LOGGER = logging.getLogger("anubis.skills.dsl_runtime")


@dataclass(frozen=True)
class DslStep:
    id: int
    action: str
    input: dict[str, Any] = field(default_factory=dict)
    save_as: str = ""
    require: str = ""


@dataclass(frozen=True)
class DslSkill:
    name: str
    trigger: str
    steps: tuple[DslStep, ...]
    fallback: DslStep | None = None


@dataclass(frozen=True)
class StepTrace:
    step: int
    action: str
    ok: bool
    output: Any = None
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class SkillResult:
    ok: bool
    skill: str
    value: Any
    trace: tuple[StepTrace, ...]
    variables: dict[str, Any]

    def log(self) -> list[dict[str, Any]]:
        return [trace.__dict__ for trace in self.trace]


class DslRuntimeError(RuntimeError):
    pass


class MemoryConnector:
    def __init__(
        self,
        search_memory: Callable[[str, int], Any] | None = None,
        query_qdrant: Callable[[str, int], Any] | None = None,
    ) -> None:
        self._search_memory = search_memory or (lambda _query, _limit=8: [])
        self._query_qdrant = query_qdrant or (lambda _query, _limit=8: [])

    def search_memory(self, query: str, limit: int = 8) -> Any:
        return self._search_memory(query, limit)

    def query_qdrant(self, query: str, limit: int = 8) -> Any:
        return self._query_qdrant(query, limit)


class LlmHandler:
    def __init__(self, call: Callable[[str, list[Any]], Any] | None = None) -> None:
        self._call = call or (lambda _prompt, _context: "")

    def call(self, prompt: str, context: list[Any]) -> Any:
        return self._call(prompt, context)


class StepLogger:
    def __init__(self, sink: Callable[[StepTrace], None] | None = None) -> None:
        self.sink = sink

    def log(self, trace: StepTrace) -> None:
        LOGGER.info("dsl_step %s", json.dumps(trace.__dict__, ensure_ascii=False, default=str))
        if self.sink:
            self.sink(trace)


class ToolDispatcher:
    def __init__(self, tools: Mapping[str, Callable[..., Any]] | None = None, allowed: set[str] | None = None) -> None:
        self.tools = dict(tools or {})
        self.allowed = set(allowed or DEFAULT_ALLOWED_TOOLS)

    def dispatch(self, name: str, args: Mapping[str, Any]) -> Any:
        if name not in self.allowed:
            raise DslRuntimeError(f"tool not whitelisted: {name}")
        if unsafe_tool_args(args):
            raise DslRuntimeError("RUN_TOOL arguments contain a forbidden execution surface")
        tool = self.tools.get(name)
        if tool is None:
            raise DslRuntimeError(f"tool not registered: {name}")
        return tool(**dict(args))

    def snapshot(self) -> dict[str, Any]:
        return {
            "allowed": sorted(self.allowed),
            "registered": sorted(self.tools),
        }


class DslRuntime:
    def __init__(
        self,
        memory: MemoryConnector | None = None,
        llm: LlmHandler | None = None,
        tools: Mapping[str, Callable[..., Any]] | None = None,
        allowed_tools: set[str] | None = None,
        logger: StepLogger | None = None,
        max_steps: int = 64,
    ) -> None:
        self.memory = memory or MemoryConnector()
        self.llm = llm or LlmHandler()
        self.dispatcher = ToolDispatcher(tools, allowed_tools)
        self.logger = logger or StepLogger()
        self.max_steps = max_steps

    def execute(self, skill: DslSkill | Mapping[str, Any], context: dict[str, Any]) -> SkillResult:
        parsed = parse_skill(skill) if isinstance(skill, Mapping) else skill
        validate_skill(parsed)
        variables: dict[str, Any] = {"input": dict(context), "query": context.get("query", "")}
        trace: list[StepTrace] = []
        step_index = {step.id: index for index, step in enumerate(parsed.steps)}
        index = 0

        if len(parsed.steps) > self.max_steps:
            raise DslRuntimeError("skill exceeds max step limit")

        while index < len(parsed.steps):
            step = parsed.steps[index]
            if step.require and not eval_condition(step.require, variables):
                self._record(trace, StepTrace(step.id, step.action, True, "skipped"))
                index += 1
                continue

            ok, output, error = self._safe_step(step, variables)
            self._record(trace, StepTrace(step.id, step.action, ok, output, error))

            if not ok:
                return self._failed(parsed, variables, trace)
            if step.save_as:
                variables[step.save_as] = output
            if step.action == "RETURN":
                return SkillResult(True, parsed.name, output, tuple(trace), variables)
            if step.action == "IF":
                next_step = output.get("then_step") if output.get("condition") else output.get("else_step")
                if next_step in (None, ""):
                    index += 1
                    continue
                next_index = step_index.get(int(next_step))
                if next_index is None or next_index <= index:
                    return self._failed(parsed, variables, trace, "invalid IF jump")
                index = next_index
                continue
            index += 1

        return SkillResult(True, parsed.name, variables.get("result"), tuple(trace), variables)

    def snapshot(self) -> dict[str, Any]:
        return {
            "actions": sorted(ALLOWED_ACTIONS),
            "tools": self.dispatcher.snapshot(),
            "max_steps": self.max_steps,
            "deterministic": True,
            "arbitrary_code_execution": False,
        }

    def _safe_step(self, step: DslStep, variables: dict[str, Any]) -> tuple[bool, Any, str]:
        try:
            return True, self._run_step(step, variables), ""
        except Exception as exc:
            return False, None, str(exc)

    def _run_step(self, step: DslStep, variables: dict[str, Any]) -> Any:
        action = step.action.upper()
        if action not in ALLOWED_ACTIONS:
            raise DslRuntimeError(f"action not allowed: {action}")
        if action == "IF":
            return {
                "condition": eval_condition(str(step.input.get("condition", "")), variables),
                "then_step": resolve(step.input.get("then_step", step.input.get("then")), variables),
                "else_step": resolve(step.input.get("else_step", step.input.get("else")), variables),
            }
        data = resolve(step.input, variables)
        if action == "SEARCH_MEMORY":
            return self.memory.search_memory(str(data.get("query", "")), int(data.get("limit", 8)))
        if action == "QUERY_QDRANT":
            return self.memory.query_qdrant(str(data.get("query", "")), int(data.get("limit", data.get("top_k", 8))))
        if action == "CALL_LLM":
            names = data.get("context", [])
            if not isinstance(names, list):
                raise DslRuntimeError("CALL_LLM context must be a list")
            return self.llm.call(str(data.get("prompt", "")), [variables.get(str(name)) for name in names])
        if action == "RUN_TOOL":
            args = data.get("args", {})
            if not isinstance(args, dict):
                raise DslRuntimeError("RUN_TOOL args must be an object")
            return self.dispatcher.dispatch(str(data.get("name", "")), args)
        if action == "THEN":
            return data.get("value", True)
        if action == "RETURN":
            return data.get("value")
        raise DslRuntimeError(f"unsupported action: {action}")

    def _failed(
        self,
        skill: DslSkill,
        variables: dict[str, Any],
        trace: list[StepTrace],
        reason: str = "",
    ) -> SkillResult:
        if skill.fallback:
            ok, output, error = self._safe_step(skill.fallback, variables)
            self._record(trace, StepTrace(skill.fallback.id, skill.fallback.action, ok, output, error))
            if ok:
                return SkillResult(True, skill.name, output, tuple(trace), variables)
        return SkillResult(False, skill.name, None, tuple(trace), {**variables, "error": reason or trace[-1].error})

    def _record(self, trace: list[StepTrace], item: StepTrace) -> None:
        trace.append(item)
        self.logger.log(item)


def parse_skill(raw: Mapping[str, Any]) -> DslSkill:
    steps = raw.get("steps", ())
    if not isinstance(steps, list | tuple):
        raise DslRuntimeError("steps must be a list")
    skill = DslSkill(
        name=str(raw.get("name") or "unnamed_skill"),
        trigger=str(raw.get("trigger", "")),
        steps=tuple(parse_step(item) for item in steps),
        fallback=parse_step(raw["fallback"]) if isinstance(raw.get("fallback"), Mapping) else None,
    )
    validate_skill(skill)
    return skill


def parse_step(raw: Mapping[str, Any]) -> DslStep:
    if not isinstance(raw, Mapping):
        raise DslRuntimeError("step must be an object")
    action = str(raw.get("action", "")).upper()
    if action not in ALLOWED_ACTIONS:
        raise DslRuntimeError(f"action not allowed: {action}")
    return DslStep(
        id=int(raw.get("id") or raw.get("step") or 0),
        action=action,
        input=dict(raw.get("input") or {}),
        save_as=str(raw.get("save_as") or ""),
        require=str(raw.get("require") or ""),
    )


def validate_skill(skill: DslSkill) -> None:
    if not skill.steps:
        raise DslRuntimeError("skill requires at least one step")
    ids = [step.id for step in skill.steps]
    if any(step_id <= 0 for step_id in ids):
        raise DslRuntimeError("step ids must be positive integers")
    if len(set(ids)) != len(ids):
        raise DslRuntimeError("step ids must be unique")
    positions = {step.id: index for index, step in enumerate(skill.steps)}
    for index, step in enumerate(skill.steps):
        if step.action == "RUN_TOOL":
            name = str(step.input.get("name", ""))
            if name and name not in DEFAULT_ALLOWED_TOOLS:
                # Runtime-level allowed_tools may be narrower or wider, but obvious raw execution names are always rejected.
                if name.lower() in {"shell", "bash", "python", "python3", "eval", "exec", "subprocess", "run_command"}:
                    raise DslRuntimeError(f"raw execution tool is forbidden: {name}")
        if step.action == "IF":
            for key in ("then_step", "then", "else_step", "else"):
                value = step.input.get(key)
                if value in (None, ""):
                    continue
                try:
                    target = int(value)
                except (TypeError, ValueError) as exc:
                    raise DslRuntimeError(f"IF {key} must reference a numeric step id") from exc
                if target not in positions:
                    raise DslRuntimeError(f"IF {key} references unknown step: {target}")
                if positions[target] <= index:
                    raise DslRuntimeError("IF jumps must move forward")


def resolve(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, variables) for item in value]
    if isinstance(value, str):
        full = re.fullmatch(r"\$\{([a-zA-Z0-9_.-]+)\}", value.strip())
        if full:
            return lookup(full.group(1), variables)
        return re.sub(r"\$\{([a-zA-Z0-9_.-]+)\}", lambda match: stringify(lookup(match.group(1), variables)), value)
    return value


def lookup(path: str, variables: dict[str, Any]) -> Any:
    value: Any = variables
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        else:
            value = getattr(value, part, None)
    return value


def eval_condition(condition: str, variables: dict[str, Any]) -> bool:
    text = condition.strip()
    match = re.fullmatch(r"(EXISTS|EMPTY)\(([^)]+)\)", text)
    if match:
        value = lookup(clean_ref(match.group(2)), variables)
        return bool(value) if match.group(1) == "EXISTS" else not bool(value)
    match = re.fullmatch(r"(CONTAINS|EQUALS)\(([^,]+),\s*['\"]?(.+?)['\"]?\)", text)
    if match:
        value = stringify(lookup(clean_ref(match.group(2)), variables))
        return match.group(3) in value if match.group(1) == "CONTAINS" else value == match.group(3)
    match = re.fullmatch(r"(GT|GTE|LT|LTE)\(([^,]+),\s*([0-9.]+)\)", text)
    if match:
        left = float(lookup(clean_ref(match.group(2)), variables) or 0)
        right = float(match.group(3))
        return {"GT": left > right, "GTE": left >= right, "LT": left < right, "LTE": left <= right}[match.group(1)]
    return False


def unsafe_tool_args(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_TOOL_ARG_KEYS:
                return True
            if unsafe_tool_args(item):
                return True
        return False
    if isinstance(value, list):
        return any(unsafe_tool_args(item) for item in value)
    if isinstance(value, str):
        return bool(FORBIDDEN_TOOL_ARG_TEXT.search(value))
    return False


def clean_ref(value: str) -> str:
    return value.strip().removeprefix("${").removesuffix("}")


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


DslInterpreter = DslRuntime
SkillExecutionEngine = DslRuntime


__all__ = [
    "ALLOWED_ACTIONS",
    "DEFAULT_ALLOWED_TOOLS",
    "DslInterpreter",
    "DslRuntime",
    "DslRuntimeError",
    "DslSkill",
    "DslStep",
    "LlmHandler",
    "MemoryConnector",
    "SkillResult",
    "SkillExecutionEngine",
    "StepLogger",
    "StepTrace",
    "ToolDispatcher",
    "parse_skill",
    "parse_step",
    "validate_skill",
]
