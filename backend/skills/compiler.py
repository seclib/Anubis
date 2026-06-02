from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from pprint import pformat
import json
import re
import textwrap
from typing import Any, Literal, Protocol


ToolName = Literal["search_memory", "read_file", "write_file", "call_llm", "sandbox_command", "noop"]
RiskLevel = Literal["low", "medium", "high", "critical"]


ALLOWED_TOOLS: set[ToolName] = {"search_memory", "read_file", "write_file", "call_llm", "sandbox_command", "noop"}
WRITE_WORDS = {"write", "save", "store", "update", "append", "record"}
READ_WORDS = {"read", "inspect", "open", "load"}
SEARCH_WORDS = {"search", "retrieve", "find", "query", "lookup", "recall"}
LLM_WORDS = {"summarize", "classify", "explain", "draft", "rewrite", "generate"}
COMMAND_WORDS = {"run", "execute", "command", "shell"}
UNSAFE_PATTERNS = (
    r"\bignore\b.{0,40}\b(system|developer|previous|instructions?)\b",
    r"\b(jailbreak|developer mode|sudo|rm\s+-rf|curl\s+.*\|\s*sh|wget\s+.*\|\s*sh)\b",
    r"\b(eval|exec|compile|__import__|subprocess|os\.system|pickle\.loads)\b",
    r"(?im)^\s*(system|developer|assistant|tool|function)\s*:",
)
SAFE_COMMANDS = {"git", "ls", "pwd", "rg", "sed", "cat", "python3", "python", "pytest"}


@dataclass(frozen=True)
class ParsedSkill:
    name: str
    path: str
    tags: tuple[str, ...]
    trigger: str
    context: str
    procedure: tuple[str, ...]
    fallback: str
    execution: tuple[str, ...]
    markdown: str


@dataclass(frozen=True)
class ExecutionStep:
    index: int
    source: str
    tool: ToolName
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    executable: bool = False


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    message: str
    risk: RiskLevel


@dataclass(frozen=True)
class CriticResult:
    approved: bool
    score: float
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class CompiledSkill:
    name: str
    source_path: str
    module_name: str
    module_code: str
    steps: tuple[ExecutionStep, ...]
    critic: CriticResult


class SkillRuntime(Protocol):
    def search_memory(self, query: str) -> Any:
        ...

    def read_file(self, path: str) -> Any:
        ...

    def write_file(self, path: str, content: str) -> Any:
        ...

    def call_llm(self, prompt: str) -> Any:
        ...

    def sandbox_command(self, command: str, justification: str) -> Any:
        ...


class SkillCompilerError(ValueError):
    pass


class SkillLike(Protocol):
    name: str
    path: str
    tags: list[str]
    when_to_use: str
    steps: list[str]
    tools: str
    markdown: str


class SkillParser:
    def parse(self, path: str, markdown: str) -> ParsedSkill:
        body = strip_frontmatter(markdown)
        name = skill_name(body, Path(path).stem)
        tags = parse_tags(body)
        context = section(markdown, "context")
        fallback = section(markdown, "fallback")
        execution = parse_lines(section(markdown, "execution"))
        procedure = tuple(parse_lines(section(markdown, "procedure") or section(markdown, "steps")))
        return ParsedSkill(
            name=name,
            path=path,
            tags=tuple(tags),
            trigger=section(markdown, "trigger") or section(markdown, "when to use"),
            context=context,
            procedure=procedure,
            fallback=fallback,
            execution=tuple(execution),
            markdown=markdown,
        )


class ToolMapper:
    def map_skill(self, skill: ParsedSkill) -> tuple[ExecutionStep, ...]:
        raw_steps = list(skill.execution) if skill.execution else list(skill.procedure)
        return tuple(self.map_step(index, step) for index, step in enumerate(raw_steps, start=1))

    def map_step(self, index: int, step: str) -> ExecutionStep:
        explicit = self._explicit_mapping(index, step)
        if explicit:
            return explicit
        terms = set(tokens(step))
        if terms & SEARCH_WORDS:
            return ExecutionStep(index, step, "search_memory", {"query": safe_query(step)}, "retrieves memory", True)
        if terms & READ_WORDS:
            return ExecutionStep(index, step, "read_file", {"path": "<context.path>"}, "reads explicit context path", False)
        if terms & WRITE_WORDS:
            return ExecutionStep(index, step, "write_file", {"path": "<context.output_path>", "content": "<context.content>"}, "writes explicit context content", False)
        if terms & LLM_WORDS:
            return ExecutionStep(index, step, "call_llm", {"prompt": safe_query(step)}, "uses model for bounded transformation", True)
        if terms & COMMAND_WORDS:
            command = extract_command(step)
            executable = bool(command and command_name(command) in SAFE_COMMANDS)
            return ExecutionStep(index, step, "sandbox_command", {"command": command or "", "justification": step[:240]}, "sandboxed command", executable)
        return ExecutionStep(index, step, "noop", {"note": step}, "procedural guidance only", False)

    def _explicit_mapping(self, index: int, step: str) -> ExecutionStep | None:
        match = re.match(r"(?i)^\s*tool\s*:\s*([a-z_]+)\s*(.*)$", step)
        if match:
            tool = match.group(1).lower()
            if tool not in ALLOWED_TOOLS:
                return ExecutionStep(index, step, "noop", {"blocked_tool": tool}, "tool is not allowed", False)
            args = parse_key_values(match.group(2))
            return ExecutionStep(index, step, tool, args, "explicit tool mapping", tool != "noop")
        match = re.match(r"(?i)^\s*command\s*:\s*(.+)$", step)
        if match:
            command = match.group(1).strip()
            executable = command_name(command) in SAFE_COMMANDS
            return ExecutionStep(index, step, "sandbox_command", {"command": command, "justification": step[:240]}, "explicit sandbox command", executable)
        return None


class SkillCritic:
    def review(self, skill: ParsedSkill, steps: tuple[ExecutionStep, ...]) -> CriticResult:
        issues: list[ValidationIssue] = []
        if not skill.name or len(skill.name) < 3:
            issues.append(ValidationIssue("structure", "skill name is missing or too short", "high"))
        if "skill" not in {tag.lower() for tag in skill.tags}:
            issues.append(ValidationIssue("structure", "skill tag is required", "medium"))
        if len(skill.trigger.split()) < 4:
            issues.append(ValidationIssue("structure", "trigger is too vague", "medium"))
        if len(skill.procedure) < 2:
            issues.append(ValidationIssue("structure", "procedure needs at least two steps", "high"))
        if not skill.fallback.strip():
            issues.append(ValidationIssue("structure", "fallback is required", "medium"))
        for label, text in [("trigger", skill.trigger), ("context", skill.context), ("fallback", skill.fallback), ("markdown", skill.markdown)]:
            for pattern in UNSAFE_PATTERNS:
                if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                    issues.append(ValidationIssue("injection", f"unsafe pattern in {label}: {pattern}", "critical"))
        for step in steps:
            issues.extend(self._review_step(step))
        deterministic = all(step.tool != "sandbox_command" or bool(step.args.get("command")) for step in steps)
        if not deterministic:
            issues.append(ValidationIssue("determinism", "sandbox command step lacks explicit command", "high"))
        score = self._score(issues, steps)
        return CriticResult(approved=score >= 0.74 and not any(issue.risk == "critical" for issue in issues), score=score, issues=tuple(issues))

    def _review_step(self, step: ExecutionStep) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if step.tool not in ALLOWED_TOOLS:
            issues.append(ValidationIssue("tool", f"tool is not whitelisted: {step.tool}", "critical"))
        if step.tool == "sandbox_command":
            command = str(step.args.get("command") or "")
            if not command:
                issues.append(ValidationIssue("tool", "sandbox command is empty", "high"))
            elif command_name(command) not in SAFE_COMMANDS:
                issues.append(ValidationIssue("tool", f"command is not whitelisted: {command_name(command)}", "critical"))
            if has_shell_injection_surface(command):
                issues.append(ValidationIssue("tool", "command contains shell control surface", "critical"))
        if step.tool in {"read_file", "write_file"}:
            path = str(step.args.get("path") or "")
            if path and path.startswith(("/", "~")):
                issues.append(ValidationIssue("tool", "absolute or home paths are not allowed in compiled skills", "high"))
        return issues

    def _score(self, issues: list[ValidationIssue], steps: tuple[ExecutionStep, ...]) -> float:
        score = 1.0
        penalties = {"low": 0.05, "medium": 0.12, "high": 0.24, "critical": 0.60}
        for issue in issues:
            score -= penalties[issue.risk]
        if not steps:
            score -= 0.35
        if any(step.executable for step in steps):
            score += 0.05
        return round(max(0.0, min(1.0, score)), 6)


class SkillModuleGenerator:
    def generate(self, skill: ParsedSkill, steps: tuple[ExecutionStep, ...], critic: CriticResult) -> str:
        payload = {
            "name": skill.name,
            "source_path": skill.path,
            "tags": list(skill.tags),
            "trigger": skill.trigger,
            "context": skill.context,
            "fallback": skill.fallback,
            "compiled_at": datetime.now(UTC).isoformat(),
            "steps": [asdict(step) for step in steps],
            "critic": {"approved": critic.approved, "score": critic.score, "issues": [asdict(issue) for issue in critic.issues]},
        }
        spec = pformat(payload, width=100, sort_dicts=False)
        class_code = textwrap.dedent(
            '''
            class Skill:
                name = SKILL_SPEC["name"]

                def trigger(self, context):
                    text = " ".join(str(value) for value in context.values()).lower() if isinstance(context, dict) else str(context).lower()
                    terms = [term for term in SKILL_SPEC["trigger"].lower().replace(",", " ").split() if len(term) > 3]
                    return any(term in text for term in terms)

                def run(self, context, runtime):
                    if not SKILL_SPEC["critic"]["approved"]:
                        return self.fallback(context, reason="compiled skill failed critic approval")
                    results = []
                    for step in SKILL_SPEC["steps"]:
                        if not step.get("executable"):
                            results.append({"step": step["index"], "tool": step["tool"], "ok": True, "skipped": True, "reason": step["reason"]})
                            continue
                        results.append(self._execute_step(step, context, runtime))
                    return {"skill": self.name, "ok": all(item.get("ok", False) for item in results), "results": results}

                def fallback(self, context, reason=""):
                    return {"skill": self.name, "ok": False, "fallback": SKILL_SPEC["fallback"], "reason": reason}

                def _execute_step(self, step, context, runtime):
                    tool = step["tool"]
                    args = self._resolve_args(step.get("args", {}), context)
                    try:
                        if tool == "search_memory":
                            value = runtime.search_memory(str(args.get("query", "")))
                        elif tool == "read_file":
                            value = runtime.read_file(str(args["path"]))
                        elif tool == "write_file":
                            value = runtime.write_file(str(args["path"]), str(args.get("content", "")))
                        elif tool == "call_llm":
                            value = runtime.call_llm(str(args.get("prompt", "")))
                        elif tool == "sandbox_command":
                            value = runtime.sandbox_command(str(args["command"]), str(args.get("justification", "compiled skill step")))
                        else:
                            value = None
                        return {"step": step["index"], "tool": tool, "ok": True, "output": value}
                    except Exception as exc:
                        return {"step": step["index"], "tool": tool, "ok": False, "error": str(exc)}

                def _resolve_args(self, args, context):
                    resolved = {}
                    for key, value in args.items():
                        if isinstance(value, str) and value.startswith("<context.") and value.endswith(">"):
                            ctx_key = value[len("<context."):-1]
                            resolved[key] = context.get(ctx_key, "")
                        else:
                            resolved[key] = value
                    return resolved
            '''
        ).strip()
        return f"from __future__ import annotations\n\nSKILL_SPEC = {spec}\n\n\n{class_code}\n"


class SkillCompiler:
    def __init__(
        self,
        parser: SkillParser | None = None,
        mapper: ToolMapper | None = None,
        critic: SkillCritic | None = None,
        generator: SkillModuleGenerator | None = None,
    ) -> None:
        self.parser = parser or SkillParser()
        self.mapper = mapper or ToolMapper()
        self.critic = critic or SkillCritic()
        self.generator = generator or SkillModuleGenerator()

    def compile_markdown(self, path: str, markdown: str) -> CompiledSkill:
        parsed = self.parser.parse(path, markdown)
        steps = self.mapper.map_skill(parsed)
        critic = self.critic.review(parsed, steps)
        module_name = module_name_for(parsed.name)
        module_code = self.generator.generate(parsed, steps, critic)
        return CompiledSkill(
            name=parsed.name,
            source_path=path,
            module_name=module_name,
            module_code=module_code,
            steps=steps,
            critic=critic,
        )

    def compile_skill(self, skill: SkillLike) -> CompiledSkill:
        return self.compile_markdown(skill.path, skill.markdown)

    def write_module(self, compiled: CompiledSkill, output_dir: Path) -> Path:
        if not compiled.critic.approved:
            raise SkillCompilerError("cannot write compiled skill that failed critic validation")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{compiled.module_name}.py"
        path.write_text(compiled.module_code, encoding="utf-8")
        return path


class SafeSkillRuntime:
    def __init__(self, tools: dict[str, Any] | None = None, sandbox: Any | None = None) -> None:
        self.tools = tools or {}
        self.sandbox = sandbox

    def search_memory(self, query: str) -> Any:
        return self._call("search_memory", query=query)

    def read_file(self, path: str) -> Any:
        return self._call("read_file", path=path)

    def write_file(self, path: str, content: str) -> Any:
        return self._call("write_file", path=path, content=content)

    def call_llm(self, prompt: str) -> Any:
        return self._call("call_llm", prompt=prompt)

    def sandbox_command(self, command: str, justification: str) -> Any:
        if command_name(command) not in SAFE_COMMANDS or has_shell_injection_surface(command):
            raise SkillCompilerError("unsafe sandbox command blocked")
        if self.sandbox is None:
            raise SkillCompilerError("sandbox executor is required for command execution")
        from backend.tools.sandbox import ToolRequest

        return self.sandbox.execute(ToolRequest(command=command, justification=justification))

    def _call(self, name: str, **kwargs: Any) -> Any:
        fn = self.tools.get(name)
        if fn is None:
            raise SkillCompilerError(f"runtime tool not registered: {name}")
        return fn(**kwargs)


def section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def parse_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        value = re.sub(r"^[-*]\s+", "", line.strip())
        value = re.sub(r"^\d+[.)]\s+", "", value)
        if value:
            lines.append(value)
    return lines


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())


def safe_query(text: str) -> str:
    value = re.sub(r"`[^`]+`", "<artifact>", text)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:500]


def extract_command(text: str) -> str:
    fenced = re.search(r"```(?:bash|sh|shell)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip().splitlines()[0].strip()
    inline = re.search(r"`([^`]+)`", text)
    if inline:
        return inline.group(1).strip()
    explicit = re.search(r"(?i)\b(?:run|execute|command)\s+(.+)$", text)
    return explicit.group(1).strip() if explicit else ""


def command_name(command: str) -> str:
    return Path(command.strip().split(maxsplit=1)[0]).name.lower() if command.strip() else ""


def has_shell_injection_surface(command: str) -> bool:
    return any(marker in command for marker in (";", "&&", "||", "|", "`", "$(", "\n", "\r", ">", "<"))


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)=(['\"])(.*?)\2|([a-zA-Z_][a-zA-Z0-9_]*)=([^\s]+)"
    for key, _quote, quoted, bare_key, bare_value in re.findall(pattern, text):
        if key:
            values[key] = quoted
        elif bare_key:
            values[bare_key] = bare_value
    if not values and text.strip():
        values["value"] = text.strip()
    return values


def module_name_for(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
    if not value:
        value = "compiled_skill"
    if value[0].isdigit():
        value = f"skill_{value}"
    return value


def strip_frontmatter(markdown: str) -> str:
    match = re.match(r"\A---\n.*?\n---\n?", markdown, flags=re.DOTALL)
    return markdown[match.end() :] if match else markdown


def skill_name(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip()
        if title.lower().startswith("skill:"):
            return title.split(":", 1)[1].strip()
        return title
    return fallback


def parse_tags(markdown: str) -> list[str]:
    for line in markdown.splitlines():
        if line.lower().startswith("tags:"):
            raw = line.split(":", 1)[1].strip().strip("[]")
            return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]
    return []


def example_compiled_skill() -> CompiledSkill:
    markdown = """# skill: memory-grounded-answer

tags: [skill, auto-generated]

## trigger
When a question requires a grounded answer from Anubis memory.

## context
The agent must retrieve memory, summarize evidence, and avoid unsupported claims.

## procedure
1. Retrieve relevant memory for the user query.
2. Summarize the retrieved evidence.
3. Validate that the answer is grounded.
4. Use fallback when memory is insufficient.

## fallback
Ask for clarification or say that grounded memory is missing.

## execution
- tool: search_memory query="<context.query>"
- tool: call_llm prompt="Summarize retrieved evidence without adding unsupported facts."
"""
    return SkillCompiler().compile_markdown("skills/memory-grounded-answer.md", markdown)


__all__ = [
    "CompiledSkill",
    "CriticResult",
    "ExecutionStep",
    "ParsedSkill",
    "SafeSkillRuntime",
    "SkillCompiler",
    "SkillCompilerError",
    "SkillLike",
    "SkillCritic",
    "SkillModuleGenerator",
    "SkillParser",
    "ToolMapper",
    "ValidationIssue",
    "example_compiled_skill",
]
