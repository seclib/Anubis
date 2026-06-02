from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from backend.skills.dsl_runtime import DslSkill, DslStep
from backend.skills.plugin_manager import PluginManager


SAFE_DSL_ACTIONS = {"SEARCH_MEMORY", "QUERY_QDRANT", "CALL_LLM", "RUN_TOOL", "IF", "RETURN"}
SAFE_TOOLS = {"search_memory", "query_qdrant", "summarize", "classify", "format_report"}
BLOCKED_TEXT = re.compile(r"(?i)(ignore previous|jailbreak|developer mode|sudo|rm\s+-rf|curl|wget|eval\(|exec\(|subprocess|__import__|socket)")
PLUGIN_ROOT = Path("skills")


class VaultLike(Protocol):
    def list_notes(self) -> list[dict[str, str]]:
        ...

    def read_note(self, note_path: str) -> str:
        ...

    def write_note(self, note_path: str, content: str) -> None:
        ...


@dataclass(frozen=True)
class SkillSignal:
    kind: str
    text: str
    confidence: float
    source: str = ""


@dataclass(frozen=True)
class SkillCandidate:
    name: str
    trigger: str
    context: str
    procedure: tuple[str, ...]
    fallback: str
    sources: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class DslDocument:
    name: str
    source_path: str
    trigger: str
    context: str
    steps: tuple[DslStep, ...]
    fallback: DslStep

    def to_skill(self) -> DslSkill:
        return DslSkill(self.name, self.trigger, self.steps, self.fallback)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "context": self.context,
            "steps": [asdict(step) for step in self.steps],
            "fallback": asdict(self.fallback),
        }

    def markdown(self) -> str:
        return "\n".join(
            [
                f"# skill: {self.name}",
                "tags: [skill, generated, self-improving]",
                "",
                "## trigger",
                self.trigger,
                "",
                "## context",
                self.context,
                "",
                "## procedure",
                *[f"{index}. {step}" for index, step in enumerate(self.procedure_text(), 1)],
                "",
                "## tools",
                "SEARCH_MEMORY, QUERY_QDRANT, CALL_LLM, RUN_TOOL, IF, RETURN",
                "",
                "## output",
                "A grounded answer or report based on retrieved memory.",
                "",
                "## dsl",
                "```json",
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )

    def procedure_text(self) -> tuple[str, ...]:
        labels = {
            "SEARCH_MEMORY": "Retrieve relevant Obsidian memory.",
            "QUERY_QDRANT": "Retrieve similar vector patterns from Qdrant.",
            "CALL_LLM": "Synthesize only from retrieved context.",
            "RUN_TOOL": "Run an approved deterministic tool.",
            "IF": "Branch on available grounded evidence.",
            "RETURN": "Return the validated result.",
        }
        return tuple(labels.get(step.action, step.action) for step in self.steps)


@dataclass(frozen=True)
class ValidationResult:
    approved: bool
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeploymentRecord:
    name: str
    path: str
    approved: bool
    score: float
    sources: tuple[str, ...]
    plugin_manifest: str = ""
    indexed: bool = False


@dataclass(frozen=True)
class FailureAnalysis:
    signals: tuple[SkillSignal, ...]
    summary: str


@dataclass(frozen=True)
class SkillGap:
    name: str
    summary: str
    candidate: SkillCandidate
    evidence: tuple[SkillSignal, ...]
    score: float


@dataclass(frozen=True)
class GeneratedSkill:
    document: DslDocument
    markdown: str
    manifest: dict[str, Any]


@dataclass(frozen=True)
class SelfImprovementRun:
    analysis: FailureAnalysis
    gaps: tuple[SkillGap, ...]
    generated: tuple[GeneratedSkill, ...]
    validations: tuple[ValidationResult, ...]
    critic_decisions: tuple[ValidationResult, ...]
    deployments: tuple[DeploymentRecord, ...]

    @property
    def approved(self) -> bool:
        return any(record.approved for record in self.deployments)


@dataclass
class SkillRegistry:
    skills: dict[str, DslSkill] = field(default_factory=dict)

    def register(self, document: DslDocument) -> None:
        self.skills[document.name] = document.to_skill()

    def get(self, name: str) -> DslSkill | None:
        return self.skills.get(name)

    def names(self) -> list[str]:
        return sorted(self.skills)


class LogSignalAnalyzer:
    def analyze(self, logs: Iterable[Mapping[str, Any]]) -> tuple[SkillSignal, ...]:
        signals: list[SkillSignal] = []
        for item in logs:
            text = str(item.get("message") or item.get("error") or item.get("task") or item)
            if item.get("ok") is False:
                signals.append(SkillSignal("failed_task", text, float(item.get("confidence", 0.2)), str(item.get("source", "log"))))
            if "missing" in text.lower() or "unknown" in text.lower():
                signals.append(SkillSignal("missing_knowledge", text, float(item.get("confidence", 0.25)), str(item.get("source", "log"))))
            if float(item.get("confidence", 1.0)) < 0.45:
                signals.append(SkillSignal("low_confidence", text, float(item.get("confidence", 0.0)), str(item.get("source", "log"))))
        repeated = Counter(clean_text(signal.text) for signal in signals)
        for signal in list(signals):
            if repeated[clean_text(signal.text)] >= 2:
                signals.append(SkillSignal("repeated_error", signal.text, signal.confidence, signal.source))
        return tuple(signals)


class FailureAnalyzer:
    def __init__(self, analyzer: LogSignalAnalyzer | None = None) -> None:
        self.analyzer = analyzer or LogSignalAnalyzer()

    def analyze(self, failures: Iterable[Mapping[str, Any]]) -> FailureAnalysis:
        signals = self.analyzer.analyze(failures)
        counts = Counter(signal.kind for signal in signals)
        summary = ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())) or "no failure signals"
        return FailureAnalysis(signals=signals, summary=summary)


class SkillCandidateExtractor:
    def extract(self, notes: Iterable[Mapping[str, str]], minimum_count: int = 2) -> list[SkillCandidate]:
        signals = [
            SkillSignal("missing_knowledge", str(note.get("content", "")), 0.35, str(note.get("path", "")))
            for note in notes
            if self._looks_like_gap(str(note.get("content", "")))
        ]
        return self.from_signals(tuple(signals), minimum_count)

    def from_signals(self, signals: tuple[SkillSignal, ...], minimum_count: int = 2) -> list[SkillCandidate]:
        buckets: dict[str, list[SkillSignal]] = {}
        for signal in signals:
            keys = keywords(signal.text)
            if not keys:
                continue
            buckets.setdefault("_".join(keys[:2]), []).append(signal)
        candidates: list[SkillCandidate] = []
        for key, items in buckets.items():
            if len(items) < minimum_count:
                continue
            name = slug(f"{key}_workflow")
            terms = key.replace("_", ", ")
            candidates.append(
                SkillCandidate(
                    name=name,
                    trigger=f"Use when a task repeatedly needs help with {terms}.",
                    context="Generated from repeated failures, missing knowledge, or low-confidence answers.",
                    procedure=(
                        "Retrieve relevant Obsidian memory for the task.",
                        "Query Qdrant for similar known patterns.",
                        "Synthesize an answer using only retrieved evidence.",
                        "Validate confidence and return a grounded result.",
                    ),
                    fallback="Insufficient grounded memory; ask for clarification or request a playbook.",
                    sources=tuple(sorted({item.source for item in items if item.source})),
                    confidence=round(min(1.0, 0.35 + len(items) * 0.18 + sum(1 - item.confidence for item in items) / max(1, len(items)) * 0.2), 3),
                )
            )
        return candidates

    def _looks_like_gap(self, text: str) -> bool:
        return bool(re.search(r"(?i)(failed|missing|unknown|low confidence|could not|no skill|need .* workflow)", text))


class SkillGapDetector:
    def __init__(self, extractor: SkillCandidateExtractor | None = None) -> None:
        self.extractor = extractor or SkillCandidateExtractor()

    def detect(
        self,
        analysis: FailureAnalysis,
        *,
        minimum_count: int = 2,
        existing_names: Iterable[str] = (),
    ) -> tuple[SkillGap, ...]:
        candidates = SkillNormalizer().normalize(
            self.extractor.from_signals(analysis.signals, minimum_count=minimum_count),
            existing_names,
        )
        gaps: list[SkillGap] = []
        for candidate in candidates:
            candidate_terms = set(keywords(" ".join((candidate.name, candidate.trigger))))
            evidence = tuple(
                signal
                for signal in analysis.signals
                if jaccard(candidate_terms, set(keywords(signal.text))) > 0
            )
            gaps.append(
                SkillGap(
                    name=candidate.name,
                    summary=f"Missing reusable skill for {candidate.name.replace('_', ' ')}",
                    candidate=candidate,
                    evidence=evidence,
                    score=candidate.confidence,
                )
            )
        return tuple(gaps)


class SkillNormalizer:
    def normalize(self, candidates: list[SkillCandidate], existing_names: Iterable[str] = ()) -> list[SkillCandidate]:
        accepted: list[SkillCandidate] = []
        signatures = [set(keywords(name)) for name in existing_names]
        for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
            normalized = self._generalize(candidate)
            signature = set(keywords(" ".join((normalized.name, normalized.trigger, *normalized.procedure))))
            if any(jaccard(signature, prior) >= 0.72 for prior in signatures):
                continue
            signatures.append(signature)
            accepted.append(normalized)
        return accepted

    def _generalize(self, candidate: SkillCandidate) -> SkillCandidate:
        return SkillCandidate(
            slug(candidate.name),
            clean_text(candidate.trigger),
            clean_text(candidate.context),
            tuple(dedupe(clean_text(step) for step in candidate.procedure)),
            clean_text(candidate.fallback),
            candidate.sources,
            candidate.confidence,
        )


class DslCompiler:
    def compile(self, candidate: SkillCandidate) -> DslDocument:
        steps = (
            DslStep(1, "SEARCH_MEMORY", {"query": "${query}", "limit": 8}, "memory"),
            DslStep(2, "QUERY_QDRANT", {"query": "${query}", "limit": 8}, "patterns"),
            DslStep(3, "IF", {"condition": "EXISTS(${memory})", "then_step": 4, "else_step": 6}),
            DslStep(4, "CALL_LLM", {"prompt": self._prompt(candidate), "context": ["memory", "patterns"]}, "answer"),
            DslStep(5, "RETURN", {"value": "${answer}"}, require="EXISTS(${answer})"),
            DslStep(6, "RETURN", {"value": candidate.fallback}),
        )
        fallback = DslStep(99, "RETURN", {"value": candidate.fallback})
        return DslDocument(candidate.name, ",".join(candidate.sources), candidate.trigger, candidate.context, steps, fallback)

    def _prompt(self, candidate: SkillCandidate) -> str:
        procedure = " ".join(candidate.procedure)
        return f"Use only retrieved memory and Qdrant patterns. Skill procedure: {procedure}"


class ObsidianSkillGenerator:
    def __init__(self, compiler: DslCompiler | None = None) -> None:
        self.compiler = compiler or DslCompiler()

    def generate(self, gap: SkillGap) -> GeneratedSkill:
        document = self.compiler.compile(gap.candidate)
        manifest = {
            "name": document.name,
            "enabled": True,
            "triggers": [document.trigger, document.name.replace("_", " "), gap.summary],
            "skills": [document.name],
            "memory": {
                "obsidian": [f"skills/{document.name}"],
                "qdrant": [document.name, "known_patterns"],
            },
            "permissions": {"tools": [], "network": False, "filesystem": "plugin-scope-only"},
            "generated": {
                "created_at": datetime.now(UTC).isoformat(),
                "source": "self_improving_system",
                "gap_score": gap.score,
                "evidence_count": len(gap.evidence),
            },
        }
        return GeneratedSkill(document=document, markdown=document.markdown(), manifest=manifest)


class SkillDslValidator:
    def validate(self, document: DslDocument, existing: Iterable[str] = ()) -> ValidationResult:
        reasons: list[str] = []
        payload = json.dumps(document.to_dict(), ensure_ascii=False)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,80}", document.name):
            reasons.append("unsafe or invalid skill name")
        if document.name in set(existing):
            reasons.append("duplicate skill name")
        if len(document.trigger.split()) < 6:
            reasons.append("trigger is too vague")
        if len(document.steps) < 3:
            reasons.append("skill requires at least three steps")
        if BLOCKED_TEXT.search(payload):
            reasons.append("unsafe text detected")
        for step in (*document.steps, document.fallback):
            reasons.extend(self._step_reasons(step))
        score = round(max(0.0, min(1.0, 1.0 - 0.15 * len(reasons))), 3)
        return ValidationResult(score >= 0.82 and not reasons, score, tuple(reasons))

    def _step_reasons(self, step: DslStep) -> list[str]:
        reasons: list[str] = []
        if step.action not in SAFE_DSL_ACTIONS:
            reasons.append(f"unsafe DSL action: {step.action}")
        if step.action == "RUN_TOOL" and str(step.input.get("name", "")) not in SAFE_TOOLS:
            reasons.append(f"unsafe runtime tool: {step.input.get('name')}")
        if step.id < 0:
            reasons.append("negative step id")
        return reasons


class SkillCritic:
    def review(self, candidate: SkillCandidate, document: DslDocument, validation: ValidationResult) -> ValidationResult:
        reasons = list(validation.reasons)
        if not validation.approved:
            return validation
        if candidate.confidence < 0.55:
            reasons.append("candidate confidence too low")
        if len(candidate.sources) == 0:
            reasons.append("candidate lacks source evidence")
        if not any(step.action in {"SEARCH_MEMORY", "QUERY_QDRANT"} for step in document.steps):
            reasons.append("skill is not memory-first")
        if not any(step.action == "CALL_LLM" for step in document.steps):
            reasons.append("skill lacks synthesis step")
        score = round(max(0.0, validation.score - 0.18 * len(reasons)), 3)
        return ValidationResult(score >= 0.82 and not reasons, score, tuple(reasons))


class SkillValidationSystem:
    def __init__(
        self,
        validator: SkillDslValidator | None = None,
        critic: SkillCritic | None = None,
    ) -> None:
        self.validator = validator or SkillDslValidator()
        self.critic = critic or SkillCritic()

    def validate(
        self,
        gap: SkillGap,
        generated: GeneratedSkill,
        *,
        existing: Iterable[str] = (),
    ) -> tuple[ValidationResult, ValidationResult]:
        validation = self.validator.validate(generated.document, existing)
        decision = self.critic.review(gap.candidate, generated.document, validation)
        return validation, decision


class PluginRegistrar:
    def __init__(
        self,
        deployer: SkillDeployer,
        manager: PluginManager | None = None,
    ) -> None:
        self.deployer = deployer
        self.manager = manager or PluginManager(root=deployer.plugin_root)

    def register(self, generated: GeneratedSkill, critic_decision: ValidationResult) -> DeploymentRecord:
        if not critic_decision.approved:
            return DeploymentRecord(
                generated.document.name,
                "",
                False,
                critic_decision.score,
                tuple(filter(None, generated.document.source_path.split(","))),
            )
        record = self.deployer.deploy(generated.document, critic_decision)
        if record.approved:
            self.manager.discover()
            self.manager.enable(generated.document.name)
        return record


class SkillDeployer:
    def __init__(
        self,
        vault: VaultLike | None = None,
        registry: SkillRegistry | None = None,
        plugin_root: Path = PLUGIN_ROOT,
        reindex: Callable[[], Any] | None = None,
        confirmed: bool = True,
    ) -> None:
        self.vault = vault
        self.registry = registry or SkillRegistry()
        self.plugin_root = plugin_root
        self.reindex = reindex or (lambda: None)
        self.confirmed = confirmed

    def deploy(self, document: DslDocument, validation: ValidationResult) -> DeploymentRecord:
        sources = tuple(filter(None, document.source_path.split(",")))
        if not validation.approved:
            return DeploymentRecord(document.name, "", False, validation.score, sources)
        if not self.confirmed:
            raise PermissionError("skill deployment requires confirmation")
        skill_path = self._write_skill(document)
        manifest_path = self._write_manifest(document)
        self.registry.register(document)
        indexed = bool(self.reindex() is not False)
        return DeploymentRecord(document.name, skill_path, True, validation.score, sources, manifest_path, indexed)

    def rollback(self, record: DeploymentRecord) -> None:
        for path in (record.path, record.plugin_manifest):
            if path and Path(path).exists():
                Path(path).unlink()
        self.registry.skills.pop(record.name, None)

    def _write_skill(self, document: DslDocument) -> str:
        path = self._inside(self.plugin_root, Path(document.name) / f"{document.name}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.markdown(), encoding="utf-8")
        if self.vault:
            self.vault.write_note(f"skills/{document.name}/{document.name}.md", document.markdown())
        return path.as_posix()

    def _write_manifest(self, document: DslDocument) -> str:
        path = self._inside(self.plugin_root, Path(f"{document.name}.plugin.json"))
        manifest = {
            "name": document.name,
            "enabled": True,
            "triggers": [document.trigger, document.name.replace("_", " ")],
            "skills": [document.name],
            "memory": {"obsidian": [f"skills/{document.name}"], "qdrant": [document.name, "known_patterns"]},
            "generated": {"created_at": datetime.now(UTC).isoformat(), "source": "self_improving_skill_pipeline"},
        }
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return path.as_posix()

    def _inside(self, root: Path, candidate: Path) -> Path:
        base = root.resolve()
        resolved = (root / candidate).resolve()
        if base != resolved and base not in resolved.parents:
            raise ValueError("path escapes plugin root")
        return resolved


class FeedbackLoop:
    def __init__(
        self,
        analyzer: LogSignalAnalyzer | None = None,
        extractor: SkillCandidateExtractor | None = None,
        normalizer: SkillNormalizer | None = None,
        compiler: DslCompiler | None = None,
        validator: SkillDslValidator | None = None,
        critic: SkillCritic | None = None,
        deployer: SkillDeployer | None = None,
    ) -> None:
        self.analyzer = analyzer or LogSignalAnalyzer()
        self.extractor = extractor or SkillCandidateExtractor()
        self.normalizer = normalizer or SkillNormalizer()
        self.compiler = compiler or DslCompiler()
        self.validator = validator or SkillDslValidator()
        self.critic = critic or SkillCritic()
        self.deployer = deployer or SkillDeployer()

    def improve_from_logs(self, logs: Iterable[Mapping[str, Any]], candidates: list[SkillCandidate] | None = None) -> list[DeploymentRecord]:
        signals = self.analyzer.analyze(logs)
        detected = candidates or self.extractor.from_signals(signals)
        return self.deploy_candidates(detected)

    def deploy_candidates(self, candidates: list[SkillCandidate]) -> list[DeploymentRecord]:
        deployments: list[DeploymentRecord] = []
        existing = self.deployer.registry.names()
        for candidate in self.normalizer.normalize(candidates, existing):
            document = self.compiler.compile(candidate)
            validation = self.validator.validate(document, existing)
            decision = self.critic.review(candidate, document, validation)
            record = self.deployer.deploy(document, decision)
            deployments.append(record)
            if record.approved:
                existing.append(record.name)
        return deployments


class SelfImprovingSkillPipeline:
    def __init__(
        self,
        vault: VaultLike | None = None,
        registry: SkillRegistry | None = None,
        reindex: Callable[[], Any] | None = None,
        confirmed: bool = True,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.deployer = SkillDeployer(vault=vault, registry=self.registry, reindex=reindex, confirmed=confirmed)
        self.feedback = FeedbackLoop(deployer=self.deployer)
        self.extractor = self.feedback.extractor
        self.normalizer = self.feedback.normalizer
        self.compiler = self.feedback.compiler
        self.validator = self.feedback.validator
        self.critic = self.feedback.critic

    def run(self, notes: Iterable[Mapping[str, str]] = (), minimum_count: int = 2) -> list[DeploymentRecord]:
        candidates = self.extractor.extract(notes, minimum_count)
        return self.feedback.deploy_candidates(candidates)

    def improve(self, logs: Iterable[Mapping[str, Any]], minimum_count: int = 2) -> list[DeploymentRecord]:
        signals = self.feedback.analyzer.analyze(logs)
        candidates = self.extractor.from_signals(signals, minimum_count)
        return self.feedback.deploy_candidates(candidates)

    def execute(self, name: str, context: dict[str, Any]) -> DslSkill:
        skill = self.registry.get(name)
        if skill is None:
            raise KeyError(f"skill not registered: {name}")
        return skill


class SelfImprovingSystem:
    """Five-stage self-improvement pipeline for safe skill generation."""

    def __init__(
        self,
        *,
        analyzer: FailureAnalyzer | None = None,
        gap_detector: SkillGapDetector | None = None,
        generator: ObsidianSkillGenerator | None = None,
        validation: SkillValidationSystem | None = None,
        deployer: SkillDeployer | None = None,
        registrar: PluginRegistrar | None = None,
    ) -> None:
        self.analyzer = analyzer or FailureAnalyzer()
        self.gap_detector = gap_detector or SkillGapDetector()
        self.generator = generator or ObsidianSkillGenerator()
        self.validation = validation or SkillValidationSystem()
        self.deployer = deployer or SkillDeployer()
        self.registrar = registrar or PluginRegistrar(self.deployer)

    def improve(
        self,
        failures: Iterable[Mapping[str, Any]],
        *,
        minimum_count: int = 2,
    ) -> SelfImprovementRun:
        analysis = self.analyzer.analyze(failures)
        existing = self.deployer.registry.names()
        gaps = self.gap_detector.detect(analysis, minimum_count=minimum_count, existing_names=existing)
        generated: list[GeneratedSkill] = []
        validations: list[ValidationResult] = []
        decisions: list[ValidationResult] = []
        deployments: list[DeploymentRecord] = []

        for gap in gaps:
            skill = self.generator.generate(gap)
            validation, decision = self.validation.validate(gap, skill, existing=existing)
            generated.append(skill)
            validations.append(validation)
            decisions.append(decision)
            if decision.approved:
                record = self.registrar.register(skill, decision)
            else:
                record = DeploymentRecord(skill.document.name, "", False, decision.score, gap.candidate.sources)
            deployments.append(record)
            if record.approved:
                existing.append(record.name)

        return SelfImprovementRun(
            analysis=analysis,
            gaps=gaps,
            generated=tuple(generated),
            validations=tuple(validations),
            critic_decisions=tuple(decisions),
            deployments=tuple(deployments),
        )


def clean_text(text: str) -> str:
    value = re.sub(r"`[^`]+`", "<artifact>", text)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<date>", value)
    value = re.sub(r"(/[A-Za-z0-9_.-]+)+", "<path>", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:1000]


def keywords(text: str) -> list[str]:
    stop = {"and", "are", "but", "for", "from", "not", "that", "the", "this", "with", "error", "failed", "missing"}
    return [word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()) if word not in stop]


def dedupe(items: Iterable[str]) -> list[str]:
    values: list[str] = []
    signatures: list[set[str]] = []
    for item in items:
        signature = set(keywords(item))
        if signature and not any(jaccard(signature, prior) >= 0.72 for prior in signatures):
            values.append(item)
            signatures.append(signature)
    return values[:8]


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_")
    return re.sub(r"_+", "_", value)[:80] or "generated_skill"


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


__all__ = [
    "DeploymentRecord",
    "DslCompiler",
    "DslDocument",
    "FeedbackLoop",
    "LogSignalAnalyzer",
    "SelfImprovingSkillPipeline",
    "SkillCandidate",
    "SkillCandidateExtractor",
    "SkillCritic",
    "SkillDeployer",
    "SkillDslValidator",
    "SkillNormalizer",
    "SkillRegistry",
    "SkillSignal",
    "ValidationResult",
]
