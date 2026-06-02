from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import re
from typing import Any, Iterable, Literal

from backend.agent.llm import LLM, OllamaLLM
from backend.rag.indexer import RagIndexer
from backend.skills.engine import SkillEngine, SkillProposal
from backend.skills.parser import Skill, SkillRepository, parse_skill_markdown
from backend.vault.service import VaultService


EvolutionAction = Literal["create", "rewrite", "merge", "deprecate", "prompt_patch", "noop"]
ImprovementKind = Literal["system_prompt", "skill", "agent_loop"]

MIN_EVIDENCE = 2
MIN_APPROVAL_SCORE = 0.70
MIN_SKILL_USEFULNESS = 0.55
DUPLICATE_THRESHOLD = 0.72
WEAK_SKILL_THRESHOLD = 0.45
UNUSED_SKILL_THRESHOLD = 0
META_DIR = "meta-agent"
PROMPT_PATCH_DIR = f"{META_DIR}/prompt-patches"
ARCHIVE_DIR = "skills/_archive"


@dataclass(frozen=True)
class RunTrace:
    path: str
    task: str
    answer: str
    actions: list[dict[str, Any]]
    skills: list[str]
    retrieved_context: list[str] = field(default_factory=list)
    accepted: bool = True


@dataclass(frozen=True)
class FailurePattern:
    key: str
    description: str
    traces: tuple[RunTrace, ...]
    severity: float
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class SkillEvaluation:
    skill: Skill
    usage_count: int
    failure_count: int
    duplicate_paths: tuple[str, ...]
    clarity_score: float
    reuse_score: float
    usefulness_score: float
    weak: bool
    unused: bool
    duplicate: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SkillRewrite:
    action: EvolutionAction
    target_path: str
    name: str
    markdown: str
    evidence: tuple[str, ...]
    rationale: str
    score: float
    merged_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptPatch:
    title: str
    markdown: str
    evidence: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class CriticResult:
    approved: bool
    score: float
    reason: str
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvolutionResult:
    traces_analyzed: int
    failure_patterns: list[dict[str, Any]]
    skill_evaluations: list[dict[str, Any]]
    approved_updates: list[dict[str, Any]]
    rejected_updates: list[dict[str, Any]]
    prompt_patches: list[str]
    indexed_notes: list[str]


def section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def tokens(text: str) -> list[str]:
    stop = {
        "agent",
        "anubis",
        "and",
        "are",
        "for",
        "from",
        "into",
        "that",
        "the",
        "this",
        "task",
        "user",
        "with",
    }
    return [
        word
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
        if len(word) > 2 and word not in stop
    ]


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", value) or "generated"


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def numbered_steps(lines: Iterable[str]) -> str:
    clean = [line.strip() for line in lines if line.strip()]
    return "\n".join(f"{index}. {line}" for index, line in enumerate(clean, start=1))


def parse_actions(markdown: str) -> list[dict[str, Any]]:
    raw = section(markdown, "actions")
    match = re.search(r"```json\s*(.*?)```", raw, re.DOTALL)
    payload = match.group(1) if match else raw
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_list_section(markdown: str, heading: str) -> list[str]:
    body = section(markdown, heading)
    values = []
    for line in body.splitlines():
        value = re.sub(r"^[-*]\s+", "", line.strip()).strip()
        if value and value.lower() != "none":
            values.append(value)
    return values


def failure_key(trace: RunTrace) -> str | None:
    if not trace.retrieved_context:
        return "memory:no_retrieval"
    if not trace.skills:
        return "skill:no_match"
    if any(action.get("ok") is False for action in trace.actions):
        failed = [str(action.get("tool") or "unknown") for action in trace.actions if action.get("ok") is False]
        return f"tool:{Counter(failed).most_common(1)[0][0]}"
    answer = trace.answer.lower()
    if "could not" in answer or "not enough" in answer or "no relevant" in answer:
        return "answer:low_confidence"
    if len(trace.answer.strip()) < 80:
        return "answer:too_short"
    return None


class FailureAnalyzer:
    def analyze(self, traces: list[RunTrace]) -> list[FailurePattern]:
        grouped: dict[str, list[RunTrace]] = defaultdict(list)
        for trace in traces:
            key = failure_key(trace)
            if key:
                grouped[key].append(trace)

        patterns: list[FailurePattern] = []
        for key, items in grouped.items():
            if len(items) < MIN_EVIDENCE:
                continue
            common = tuple(token for token, _ in Counter(token for trace in items for token in tokens(trace.task)).most_common(8))
            severity = min(1.0, 0.35 + (len(items) / max(3, len(traces))) + failure_weight(key))
            patterns.append(
                FailurePattern(
                    key=key,
                    description=describe_failure(key, common),
                    traces=tuple(items),
                    severity=round(severity, 6),
                    tokens=common,
                )
            )
        return sorted(patterns, key=lambda pattern: pattern.severity, reverse=True)


class SkillEvaluator:
    def evaluate(self, skills: list[Skill], traces: list[RunTrace]) -> list[SkillEvaluation]:
        usage = self._usage(skills, traces)
        failures = self._failures(skills, traces)
        duplicates = self._duplicates(skills)
        evaluations = []
        for skill in skills:
            clarity = self._clarity(skill)
            reuse = self._reuse(skill, usage.get(skill.path, 0))
            usefulness = round((0.40 * clarity) + (0.35 * reuse) + (0.25 * max(0.0, 1.0 - failures.get(skill.path, 0) / 4)), 6)
            reasons: list[str] = []
            if clarity < 0.55:
                reasons.append("unclear or shallow procedure")
            if usage.get(skill.path, 0) <= UNUSED_SKILL_THRESHOLD:
                reasons.append("unused in recent traces")
            if failures.get(skill.path, 0) >= 2:
                reasons.append("associated with repeated failures")
            if duplicates.get(skill.path):
                reasons.append("duplicates another skill")
            evaluations.append(
                SkillEvaluation(
                    skill=skill,
                    usage_count=usage.get(skill.path, 0),
                    failure_count=failures.get(skill.path, 0),
                    duplicate_paths=tuple(duplicates.get(skill.path, ())),
                    clarity_score=clarity,
                    reuse_score=reuse,
                    usefulness_score=usefulness,
                    weak=usefulness < WEAK_SKILL_THRESHOLD or clarity < 0.55 or failures.get(skill.path, 0) >= 2,
                    unused=usage.get(skill.path, 0) <= UNUSED_SKILL_THRESHOLD,
                    duplicate=bool(duplicates.get(skill.path)),
                    reasons=tuple(reasons),
                )
            )
        return sorted(evaluations, key=lambda item: item.usefulness_score)

    def _usage(self, skills: list[Skill], traces: list[RunTrace]) -> dict[str, int]:
        usage = {skill.path: 0 for skill in skills}
        for trace in traces:
            haystack = "\n".join(trace.skills).lower()
            for skill in skills:
                if skill.name.lower() in haystack or skill.path.lower() in haystack:
                    usage[skill.path] += 1
        return usage

    def _failures(self, skills: list[Skill], traces: list[RunTrace]) -> dict[str, int]:
        failures = {skill.path: 0 for skill in skills}
        for trace in traces:
            if not failure_key(trace):
                continue
            haystack = "\n".join(trace.skills).lower()
            for skill in skills:
                if skill.name.lower() in haystack or skill.path.lower() in haystack:
                    failures[skill.path] += 1
        return failures

    def _duplicates(self, skills: list[Skill]) -> dict[str, list[str]]:
        duplicate_map: dict[str, list[str]] = defaultdict(list)
        signatures = {
            skill.path: set(tokens(" ".join([skill.name, skill.when_to_use, " ".join(skill.steps)])))
            for skill in skills
        }
        for left in skills:
            for right in skills:
                if left.path >= right.path:
                    continue
                if jaccard(signatures[left.path], signatures[right.path]) >= DUPLICATE_THRESHOLD:
                    duplicate_map[left.path].append(right.path)
                    duplicate_map[right.path].append(left.path)
        return duplicate_map

    def _clarity(self, skill: Skill) -> float:
        has_trigger = 1.0 if len(skill.when_to_use.split()) >= 6 else 0.25
        step_count = min(1.0, len(skill.steps) / 5)
        specific_steps = sum(1 for step in skill.steps if len(tokens(step)) >= 3)
        step_quality = min(1.0, specific_steps / max(1, len(skill.steps)))
        return round((0.30 * has_trigger) + (0.35 * step_count) + (0.35 * step_quality), 6)

    def _reuse(self, skill: Skill, usage_count: int) -> float:
        broad_trigger = 0.75 if not re.search(r"\b\d{4}-\d{2}-\d{2}\b|/[A-Za-z0-9_.-]+", skill.markdown) else 0.35
        return round((0.65 * min(1.0, usage_count / 4)) + (0.35 * broad_trigger), 6)


class SkillRewriter:
    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm or OllamaLLM()

    def create_missing_skill(self, pattern: FailurePattern) -> SkillRewrite:
        topic = "-".join(pattern.tokens[:4]) or pattern.key.replace(":", "-")
        name = f"{topic}-recovery-workflow"
        steps = self._llm_steps(pattern) or self._default_steps(pattern)
        markdown = skill_markdown(
            name=name,
            trigger=f"When tasks show repeated {pattern.description}.",
            context=f"Prevents recurring failures matching {pattern.key} by using a generalized recovery workflow.",
            procedure=steps,
            fallback="If the recovery workflow cannot ground the answer, ask for clarification and do not invent missing facts.",
        )
        return SkillRewrite(
            action="create",
            target_path=f"skills/{slug(name)}.md",
            name=name,
            markdown=markdown,
            evidence=tuple(trace.path for trace in pattern.traces),
            rationale=pattern.description,
            score=pattern.severity,
        )

    def rewrite_weak_skill(self, evaluation: SkillEvaluation) -> SkillRewrite:
        skill = evaluation.skill
        name = skill.name
        trigger = generalize_trigger(skill.when_to_use or f"When a task requires {name}.")
        context = f"Improves the reusable workflow for {name} by clarifying trigger, procedure, and fallback."
        steps = self._rewrite_steps(skill, evaluation)
        markdown = skill_markdown(
            name=name,
            trigger=trigger,
            context=context,
            procedure=steps,
            fallback="If the skill does not fit the task, retrieve related Obsidian notes and use a better matching skill before acting.",
        )
        return SkillRewrite(
            action="rewrite",
            target_path=skill.path,
            name=name,
            markdown=markdown,
            evidence=tuple(evaluation.reasons),
            rationale="; ".join(evaluation.reasons) or "skill procedure needs refinement",
            score=max(0.0, 1.0 - evaluation.usefulness_score),
        )

    def merge_duplicate_skills(self, primary: SkillEvaluation, skills_by_path: dict[str, Skill]) -> SkillRewrite | None:
        duplicate_paths = [path for path in primary.duplicate_paths if path in skills_by_path]
        if not duplicate_paths:
            return None
        skills = [primary.skill, *[skills_by_path[path] for path in duplicate_paths]]
        best = max(skills, key=lambda skill: len(skill.steps) + len(skill.when_to_use.split()))
        merged_steps = dedupe_steps(step for skill in skills for step in skill.steps)
        trigger = "When a task matches any of these related workflows: " + ", ".join(skill.name for skill in skills[:4]) + "."
        markdown = skill_markdown(
            name=best.name,
            trigger=trigger,
            context="Merged duplicate skills into one reusable workflow.",
            procedure=merged_steps,
            fallback="If the merged procedure is ambiguous, inspect the original archived skill notes and ask for clarification.",
        )
        return SkillRewrite(
            action="merge",
            target_path=best.path,
            name=best.name,
            markdown=markdown,
            evidence=tuple(skill.path for skill in skills),
            rationale="duplicate skill consolidation",
            score=0.85,
            merged_paths=tuple(path for path in duplicate_paths if path != best.path),
        )

    def deprecate_unused_skill(self, evaluation: SkillEvaluation) -> SkillRewrite:
        skill = evaluation.skill
        markdown = skill.markdown.rstrip() + "\n\n## status\nDeprecated by Anubis meta-agent because it was unused in recent validated traces.\n"
        return SkillRewrite(
            action="deprecate",
            target_path=skill.path,
            name=skill.name,
            markdown=markdown,
            evidence=("unused in recent traces",),
            rationale="unused skill",
            score=0.55,
        )

    def prompt_patch(self, patterns: list[FailurePattern]) -> PromptPatch | None:
        if not patterns:
            return None
        evidence = tuple(trace.path for pattern in patterns[:3] for trace in pattern.traces[:3])
        if len(set(evidence)) < MIN_EVIDENCE:
            return None
        lines = [
            "# prompt patch: validated failure recovery guidance",
            "",
            "kind: system_prompt",
            "status: proposed",
            "",
            "## validation rule",
            "This patch must be reviewed before being copied into a core system prompt.",
            "",
            "## proposed guidance",
            "- Before answering, verify that retrieved memory supports each factual claim.",
            "- When retrieval is weak, ask for clarification instead of filling gaps from prior knowledge.",
            "- When a tool call fails, inspect the failure once, retrieve fresh context, and re-plan before retrying.",
            "",
            "## evidence",
        ]
        lines.extend(f"- {path}" for path in sorted(set(evidence)))
        return PromptPatch(
            title="validated failure recovery guidance",
            markdown="\n".join(lines) + "\n",
            evidence=tuple(sorted(set(evidence))),
            score=0.78,
        )

    def _llm_steps(self, pattern: FailurePattern) -> list[str]:
        prompt = {
            "role": "skill_rewriter",
            "task": "Create generalized reusable skill steps from repeated failures.",
            "failure": asdict(pattern),
            "rules": ["return JSON array of strings", "avoid file-specific overfitting", "minimum 4 steps", "maximum 8 steps"],
        }
        return parse_llm_steps(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))

    def _default_steps(self, pattern: FailurePattern) -> list[str]:
        topic = ", ".join(pattern.tokens[:4]) or pattern.key
        return [
            f"Recognize the recurring failure pattern involving {topic}.",
            "Retrieve relevant Obsidian truth notes, Qdrant semantic context, and matching skills before acting.",
            "Identify the missing evidence, failed tool behavior, or weak skill that caused the failure.",
            "Apply the smallest corrective step and avoid repeating identical failed actions.",
            "Validate the answer or action against retrieved evidence before returning it.",
            "Record reusable learning only after the critic approves the result.",
        ]

    def _rewrite_steps(self, skill: Skill, evaluation: SkillEvaluation) -> list[str]:
        prompt = {
            "role": "skill_rewriter",
            "task": "Rewrite a weak skill into a reusable production skill.",
            "skill": skill.as_context(),
            "reasons": evaluation.reasons,
            "rules": ["return JSON array of strings", "generalize", "include validation", "include fallback behavior"],
        }
        llm_steps = parse_llm_steps(self.llm.generate(json.dumps(prompt, ensure_ascii=False)))
        if llm_steps:
            return llm_steps
        existing = dedupe_steps(skill.steps)
        if len(existing) < 4:
            existing.extend(
                [
                    "Retrieve relevant memory and existing skills before applying the procedure.",
                    "Check whether the current task actually matches the skill trigger.",
                    "Validate the result against the user request and retrieved evidence.",
                    "Escalate to clarification when evidence is missing or contradictory.",
                ]
            )
        return dedupe_steps(existing)[:8]


class EvolutionCritic:
    def __init__(self, repository: SkillRepository | None = None) -> None:
        self.repository = repository or SkillRepository()

    def review_rewrite(self, rewrite: SkillRewrite, existing: list[Skill]) -> CriticResult:
        risks: list[str] = []
        parsed = parse_skill_markdown(rewrite.target_path, rewrite.markdown)
        if rewrite.action in {"create", "rewrite", "merge"}:
            if len(parsed.when_to_use.split()) < 6:
                risks.append("trigger too vague")
            if len(parsed.steps) < 4:
                risks.append("procedure too short")
            if not section(rewrite.markdown, "fallback"):
                risks.append("missing fallback")
            if overfits(rewrite.markdown):
                risks.append("overfits to a single task")
            if unsafe_text(rewrite.markdown):
                risks.append("unsafe instruction found")
            if rewrite.action == "create" and duplicates_existing(parsed, existing):
                risks.append("duplicates existing skill")
        if rewrite.action == "deprecate" and rewrite.score < 0.50:
            risks.append("deprecation confidence too low")
        evidence_count = len(set(rewrite.evidence))
        if rewrite.action != "deprecate" and evidence_count < MIN_EVIDENCE:
            risks.append("not enough evidence")
        base = rewrite.score
        structure_bonus = 0.15 if len(parsed.steps) >= 4 else 0.0
        evidence_bonus = min(0.20, evidence_count * 0.05)
        score = round(max(0.0, min(1.0, base + structure_bonus + evidence_bonus - len(risks) * 0.20)), 6)
        return CriticResult(
            approved=score >= MIN_APPROVAL_SCORE and not risks,
            score=score,
            reason="approved" if score >= MIN_APPROVAL_SCORE and not risks else "rejected",
            risks=tuple(risks),
        )

    def review_prompt_patch(self, patch: PromptPatch) -> CriticResult:
        risks: list[str] = []
        if len(set(patch.evidence)) < MIN_EVIDENCE:
            risks.append("not enough evidence")
        if unsafe_text(patch.markdown):
            risks.append("unsafe prompt patch")
        if "status: proposed" not in patch.markdown:
            risks.append("prompt patch must remain proposed")
        score = round(max(0.0, min(1.0, patch.score - len(risks) * 0.25)), 6)
        return CriticResult(score >= MIN_APPROVAL_SCORE and not risks, score, "approved" if not risks else "rejected", tuple(risks))


class ObsidianSkillUpdater:
    def __init__(self, vault: VaultService | None = None, indexer: RagIndexer | None = None) -> None:
        self.vault = vault or VaultService()
        self.indexer = indexer or RagIndexer()

    def apply(self, rewrite: SkillRewrite) -> list[str]:
        indexed: list[str] = []
        if rewrite.action == "create":
            path = self.unique_path(rewrite.target_path)
            self.vault.write_note(path, rewrite.markdown)
            self.indexer.index_note(path)
            indexed.append(path)
            return indexed
        if rewrite.action in {"rewrite", "merge", "deprecate"}:
            self.vault.write_note(rewrite.target_path, rewrite.markdown)
            self.indexer.index_note(rewrite.target_path)
            indexed.append(rewrite.target_path)
        if rewrite.action == "merge":
            for path in rewrite.merged_paths:
                archived = f"{ARCHIVE_DIR}/{slug(path)}.md"
                try:
                    original = self.vault.read_note(path)
                except FileNotFoundError:
                    continue
                self.vault.write_note(archived, original.rstrip() + f"\n\n## status\nMerged into {rewrite.target_path}.\n")
                self.indexer.index_note(archived)
                indexed.append(archived)
        return indexed

    def save_prompt_patch(self, patch: PromptPatch) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = f"{PROMPT_PATCH_DIR}/{timestamp}-{slug(patch.title)}.md"
        self.vault.write_note(path, patch.markdown)
        self.indexer.index_note(path)
        return path

    def unique_path(self, target_path: str) -> str:
        existing = {note["path"] for note in self.vault.list_notes()}
        if target_path not in existing:
            return target_path
        base, _, suffix = target_path.rpartition(".")
        extension = f".{suffix}" if suffix else ".md"
        stem = base or target_path.removesuffix(extension)
        counter = 2
        while f"{stem}-{counter}{extension}" in existing:
            counter += 1
        return f"{stem}-{counter}{extension}"


class MetaAgent:
    def __init__(
        self,
        llm: LLM | None = None,
        vault: VaultService | None = None,
        indexer: RagIndexer | None = None,
        skill_engine: SkillEngine | None = None,
        repository: SkillRepository | None = None,
    ) -> None:
        self.llm = llm or OllamaLLM()
        self.vault = vault or VaultService()
        self.indexer = indexer or RagIndexer()
        self.repository = repository or SkillRepository()
        self.skill_engine = skill_engine or SkillEngine(llm=self.llm, vault=self.vault, indexer=self.indexer)
        self.failure_analyzer = FailureAnalyzer()
        self.skill_evaluator = SkillEvaluator()
        self.rewriter = SkillRewriter(self.llm)
        self.critic = EvolutionCritic(self.repository)
        self.updater = ObsidianSkillUpdater(self.vault, self.indexer)

    def run(self, limit: int = 50, apply_updates: bool = True) -> EvolutionResult:
        traces = self.load_traces(limit=limit)
        skills = self.repository.list_skills()
        patterns = self.failure_analyzer.analyze(traces)
        evaluations = self.skill_evaluator.evaluate(skills, traces)
        rewrites = self.propose_rewrites(patterns, evaluations, skills)
        approved: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        indexed_notes: list[str] = []

        for rewrite in rewrites:
            review = self.critic.review_rewrite(rewrite, skills)
            record = {"rewrite": asdict(rewrite), "critic": asdict(review)}
            if not review.approved:
                rejected.append(record)
                continue
            approved.append(record)
            if apply_updates:
                indexed_notes.extend(self.updater.apply(rewrite))

        prompt_paths: list[str] = []
        patch = self.rewriter.prompt_patch(patterns)
        if patch:
            patch_review = self.critic.review_prompt_patch(patch)
            if patch_review.approved and apply_updates:
                prompt_paths.append(self.updater.save_prompt_patch(patch))

        return EvolutionResult(
            traces_analyzed=len(traces),
            failure_patterns=[asdict(pattern) for pattern in patterns],
            skill_evaluations=[self._evaluation_dict(evaluation) for evaluation in evaluations],
            approved_updates=approved,
            rejected_updates=rejected,
            prompt_patches=prompt_paths,
            indexed_notes=indexed_notes,
        )

    def analyze(self, limit: int = 30, auto_skill: bool = False) -> dict[str, Any]:
        result = self.run(limit=limit, apply_updates=auto_skill)
        return asdict(result)

    def propose_rewrites(
        self,
        patterns: list[FailurePattern],
        evaluations: list[SkillEvaluation],
        skills: list[Skill],
    ) -> list[SkillRewrite]:
        rewrites: list[SkillRewrite] = []
        skills_by_path = {skill.path: skill for skill in skills}
        seen_targets: set[tuple[str, EvolutionAction]] = set()

        for pattern in patterns:
            if pattern.key in {"skill:no_match", "memory:no_retrieval", "answer:low_confidence"}:
                rewrite = self.rewriter.create_missing_skill(pattern)
                rewrites.append(rewrite)

        for evaluation in evaluations:
            key = (evaluation.skill.path, "merge")
            if evaluation.duplicate and key not in seen_targets:
                rewrite = self.rewriter.merge_duplicate_skills(evaluation, skills_by_path)
                if rewrite:
                    rewrites.append(rewrite)
                    seen_targets.add(key)
                    continue
            if evaluation.weak:
                key = (evaluation.skill.path, "rewrite")
                if key not in seen_targets:
                    rewrites.append(self.rewriter.rewrite_weak_skill(evaluation))
                    seen_targets.add(key)
            elif evaluation.unused and evaluation.usefulness_score < MIN_SKILL_USEFULNESS:
                key = (evaluation.skill.path, "deprecate")
                if key not in seen_targets:
                    rewrites.append(self.rewriter.deprecate_unused_skill(evaluation))
                    seen_targets.add(key)

        return dedupe_rewrites(rewrites)

    def load_traces(self, limit: int = 50) -> list[RunTrace]:
        notes = [
            note
            for note in self.vault.list_notes()
            if note["path"].startswith("agent-runs/") and note["path"].endswith(".md")
        ][-limit:]
        traces: list[RunTrace] = []
        for note in notes:
            text = self.vault.read_note(note["path"])
            traces.append(
                RunTrace(
                    path=note["path"],
                    task=section(text, "task"),
                    answer=section(text, "answer"),
                    actions=parse_actions(text),
                    skills=parse_list_section(text, "retrieved skills"),
                    retrieved_context=parse_list_section(text, "retrieved context"),
                    accepted="accepted: false" not in text.lower(),
                )
            )
        return traces

    def _evaluation_dict(self, evaluation: SkillEvaluation) -> dict[str, Any]:
        payload = asdict(evaluation)
        payload["skill"] = {
            "name": evaluation.skill.name,
            "path": evaluation.skill.path,
            "tags": evaluation.skill.tags,
        }
        return payload


def describe_failure(key: str, common: tuple[str, ...]) -> str:
    topic = ", ".join(common[:4]) or "recent tasks"
    if key == "memory:no_retrieval":
        return f"missing or weak retrieval for {topic}"
    if key == "skill:no_match":
        return f"missing reusable skill coverage for {topic}"
    if key == "answer:low_confidence":
        return f"low-confidence answers for {topic}"
    if key == "answer:too_short":
        return f"underspecified final answers for {topic}"
    if key.startswith("tool:"):
        return f"repeated tool failure in {key.split(':', 1)[1]} for {topic}"
    return f"recurring failure pattern for {topic}"


def failure_weight(key: str) -> float:
    if key == "memory:no_retrieval":
        return 0.25
    if key == "skill:no_match":
        return 0.20
    if key.startswith("tool:"):
        return 0.18
    return 0.12


def skill_markdown(name: str, trigger: str, context: str, procedure: list[str], fallback: str) -> str:
    return "\n".join(
        [
            f"# skill: {name}",
            "",
            "tags: [auto-generated, skill]",
            "",
            "## trigger",
            trigger.strip(),
            "",
            "## context",
            context.strip(),
            "",
            "## procedure",
            numbered_steps(procedure),
            "",
            "## fallback",
            fallback.strip(),
            "",
        ]
    )


def parse_llm_steps(response: str) -> list[str]:
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()][:8]


def generalize_trigger(trigger: str) -> str:
    value = re.sub(r"`[^`]+`", "<artifact>", trigger)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<date>", value)
    value = re.sub(r"(/[A-Za-z0-9_.-]+)+", "<path>", value)
    if not value.lower().startswith("when"):
        value = f"When {value[:1].lower()}{value[1:]}"
    return value


def dedupe_steps(steps: Iterable[str]) -> list[str]:
    accepted: list[str] = []
    signatures: list[set[str]] = []
    for step in steps:
        clean = re.sub(r"^\d+[.)]\s+", "", str(step).strip())
        if not clean:
            continue
        signature = set(tokens(clean))
        if not signature:
            continue
        if any(jaccard(signature, existing) >= 0.70 for existing in signatures):
            continue
        signatures.append(signature)
        accepted.append(clean)
        if len(accepted) >= 8:
            break
    return accepted


def duplicates_existing(candidate: Skill, existing: list[Skill]) -> bool:
    candidate_terms = set(tokens(" ".join([candidate.name, candidate.when_to_use, " ".join(candidate.steps)])))
    for skill in existing:
        skill_terms = set(tokens(" ".join([skill.name, skill.when_to_use, " ".join(skill.steps)])))
        if candidate.path != skill.path and jaccard(candidate_terms, skill_terms) >= DUPLICATE_THRESHOLD:
            return True
    return False


def overfits(markdown: str) -> bool:
    paths = len(re.findall(r"(/[A-Za-z0-9_.-]+)+", markdown))
    dates = len(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", markdown))
    hashes = len(re.findall(r"\b[a-f0-9]{12,}\b", markdown.lower()))
    return paths + dates + hashes > 5


def unsafe_text(markdown: str) -> bool:
    lowered = markdown.lower()
    blocked = [
        "ignore system",
        "ignore previous",
        "disable validation",
        "skip critic",
        "run rm",
        "sudo ",
        "curl ",
        "wget ",
        "exfiltrate",
    ]
    return any(term in lowered for term in blocked)


def dedupe_rewrites(rewrites: list[SkillRewrite]) -> list[SkillRewrite]:
    accepted: list[SkillRewrite] = []
    seen: set[tuple[str, EvolutionAction]] = set()
    for rewrite in sorted(rewrites, key=lambda item: item.score, reverse=True):
        key = (rewrite.target_path, rewrite.action)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(rewrite)
    return accepted[:12]


__all__ = [
    "CriticResult",
    "EvolutionCritic",
    "EvolutionResult",
    "FailureAnalyzer",
    "FailurePattern",
    "MetaAgent",
    "ObsidianSkillUpdater",
    "PromptPatch",
    "RunTrace",
    "SkillEvaluation",
    "SkillEvaluator",
    "SkillRewrite",
    "SkillRewriter",
]
