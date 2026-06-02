from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


class SignalType(str, Enum):
    FAILED_TASK = "failed_task"
    REPEATED_ERROR = "repeated_error"
    MISSING_KNOWLEDGE = "missing_knowledge"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class SkillSignal:
    kind: SignalType
    text: str
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillGap:
    name: str
    summary: str
    evidence: tuple[SkillSignal, ...]
    score: float
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class PluginSuggestion:
    name: str
    reason: str
    triggers: tuple[str, ...]
    skills: tuple[str, ...]
    obsidian_namespaces: tuple[str, ...]
    qdrant_namespaces: tuple[str, ...]
    gap: SkillGap


@dataclass(frozen=True)
class GeneratedPlugin:
    suggestion: PluginSuggestion
    manifest: dict[str, Any]
    files: dict[str, str]


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    message: str
    severity: str


@dataclass(frozen=True)
class ValidationResult:
    approved: bool
    score: float
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class CriticDecision:
    approved: bool
    reason: str
    score: float


@dataclass(frozen=True)
class InstallRecord:
    plugin_name: str
    installed_at: str
    files: tuple[str, ...]
    backup_dir: str
    manifest_hash: str


class SafetyGuard:
    BLOCKED = (
        "subprocess",
        "os.system",
        "socket",
        "requests",
        "urllib",
        "eval(",
        "exec(",
        "__import__",
        "rm -rf",
        "curl ",
        "wget ",
    )

    def assert_safe_text(self, text: str) -> None:
        lowered = text.lower()
        if any(token in lowered for token in self.BLOCKED):
            raise ValueError("unsafe plugin content rejected")

    def assert_inside(self, root: Path, candidate: Path) -> Path:
        base = root.resolve()
        resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if base != resolved and base not in resolved.parents:
            raise ValueError("path escapes plugin root")
        return resolved


class SkillGapDetector:
    STOPWORDS = {
        "about",
        "after",
        "again",
        "could",
        "error",
        "failed",
        "missing",
        "please",
        "response",
        "skill",
        "task",
        "there",
        "this",
        "with",
    }

    def detect(self, signals: tuple[SkillSignal, ...], minimum_score: float = 0.45) -> tuple[SkillGap, ...]:
        buckets: dict[str, list[SkillSignal]] = {}
        for signal in signals:
            keywords = self._keywords(signal.text)
            if not keywords:
                continue
            for key in keywords[:3]:
                buckets.setdefault(key, []).append(signal)
        gaps: list[SkillGap] = []
        for key, items in buckets.items():
            score = self._score(items)
            if score < minimum_score:
                continue
            keywords = tuple(key.split("_"))
            gaps.append(
                SkillGap(
                    name=f"{key}_plugin",
                    summary=f"Repeated need for {', '.join(keywords)} capability",
                    evidence=tuple(items),
                    score=round(score, 3),
                    keywords=keywords,
                )
            )
        return tuple(sorted(gaps, key=lambda gap: gap.score, reverse=True))

    def _keywords(self, text: str) -> tuple[str, ...]:
        words = [word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)]
        counts = {}
        for word in words:
            if word not in self.STOPWORDS:
                counts[word] = counts.get(word, 0) + 1
        return tuple(word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5])

    def _score(self, signals: list[SkillSignal]) -> float:
        weight = {
            SignalType.FAILED_TASK: 0.3,
            SignalType.REPEATED_ERROR: 0.28,
            SignalType.MISSING_KNOWLEDGE: 0.25,
            SignalType.LOW_CONFIDENCE: 0.2,
        }
        base = min(1.0, len(signals) / 4)
        severity = sum(weight[item.kind] + max(0.0, 1 - item.confidence) * 0.1 for item in signals)
        return min(1.0, base * 0.45 + severity / max(1, len(signals)))


class PluginSuggestionEngine:
    def suggest(self, gaps: tuple[SkillGap, ...]) -> tuple[PluginSuggestion, ...]:
        suggestions: list[PluginSuggestion] = []
        for gap in gaps:
            name = _slug(gap.name.removesuffix("_plugin"))
            triggers = tuple(dict.fromkeys((*gap.keywords, gap.summary.lower(), f"{name} workflow")))
            suggestions.append(
                PluginSuggestion(
                    name=name,
                    reason=gap.summary,
                    triggers=triggers,
                    skills=(name,),
                    obsidian_namespaces=(f"skills/{name}", f"procedures/{name}"),
                    qdrant_namespaces=(name, "known_patterns"),
                    gap=gap,
                )
            )
        return tuple(suggestions)


class PluginGenerator:
    def generate(self, suggestion: PluginSuggestion) -> GeneratedPlugin:
        skill_path = f"{suggestion.name}/README.md"
        manifest = {
            "name": suggestion.name,
            "enabled": True,
            "triggers": list(suggestion.triggers),
            "skills": list(suggestion.skills),
            "memory": {
                "obsidian": list(suggestion.obsidian_namespaces),
                "qdrant": list(suggestion.qdrant_namespaces),
            },
            "permissions": {
                "network": False,
                "shell": False,
                "filesystem": "plugin-scope-only",
                "mode": "defensive",
            },
            "generated": {
                "created_at": datetime.now(UTC).isoformat(),
                "reason": suggestion.reason,
                "source": "self_improving_plugin_system",
            },
        }
        markdown = self._skill_markdown(suggestion)
        return GeneratedPlugin(suggestion=suggestion, manifest=manifest, files={skill_path: markdown})

    def _skill_markdown(self, suggestion: PluginSuggestion) -> str:
        evidence = "\n".join(f"- {signal.kind.value}: {signal.text}" for signal in suggestion.gap.evidence[:6])
        triggers = ", ".join(suggestion.triggers[:6])
        return f"""# skill: {suggestion.name}
tags: [skill, generated, defensive]

## trigger
Use when the task involves {triggers}.

## context
This generated skill pack addresses a detected capability gap in Anubis.

## procedure
1. Retrieve relevant Obsidian playbooks and Qdrant patterns.
2. Analyze the user task against known defensive procedures.
3. Identify missing context before acting.
4. Produce a defensive recommendation or incident-oriented summary.

## fallback
Ask for clarification and avoid unsupported claims.

## source evidence
{evidence}
"""


class PluginValidator:
    REQUIRED_MANIFEST_KEYS = {"name", "enabled", "triggers", "skills", "memory", "permissions"}

    def __init__(self, guard: SafetyGuard | None = None) -> None:
        self.guard = guard or SafetyGuard()

    def validate(self, plugin: GeneratedPlugin) -> ValidationResult:
        issues: list[ValidationIssue] = []
        manifest = plugin.manifest
        missing = self.REQUIRED_MANIFEST_KEYS - set(manifest)
        for key in missing:
            issues.append(ValidationIssue("manifest", f"missing required key: {key}", "high"))
        name = str(manifest.get("name", ""))
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", name):
            issues.append(ValidationIssue("manifest", "plugin name must be a safe slug", "high"))
        if not manifest.get("triggers"):
            issues.append(ValidationIssue("manifest", "at least one trigger is required", "high"))
        permissions = manifest.get("permissions", {})
        if permissions.get("network") or permissions.get("shell"):
            issues.append(ValidationIssue("safety", "network and shell permissions are forbidden", "critical"))
        memory = manifest.get("memory", {})
        if not isinstance(memory, dict) or not memory.get("obsidian") or not memory.get("qdrant"):
            issues.append(ValidationIssue("memory", "obsidian and qdrant bindings are required", "medium"))
        for path, content in plugin.files.items():
            try:
                self.guard.assert_safe_text(path)
                self.guard.assert_safe_text(content)
            except ValueError as exc:
                issues.append(ValidationIssue("safety", str(exc), "critical"))
            if not path.endswith(".md"):
                issues.append(ValidationIssue("files", "generated skill files must be markdown", "medium"))
        score = self._score(issues)
        approved = score >= 0.78 and not any(issue.severity == "critical" for issue in issues)
        return ValidationResult(approved, score, tuple(issues))

    def _score(self, issues: list[ValidationIssue]) -> float:
        penalties = {"low": 0.05, "medium": 0.12, "high": 0.25, "critical": 0.7}
        score = 1.0
        for issue in issues:
            score -= penalties.get(issue.severity, 0.1)
        return round(max(0.0, min(1.0, score)), 3)


class PluginCritic:
    def review(self, plugin: GeneratedPlugin, validation: ValidationResult) -> CriticDecision:
        if not validation.approved:
            return CriticDecision(False, "validation failed", validation.score)
        evidence_count = len(plugin.suggestion.gap.evidence)
        if evidence_count < 2:
            return CriticDecision(False, "insufficient repeated evidence for auto-install", min(validation.score, 0.6))
        if plugin.suggestion.gap.score < 0.5:
            return CriticDecision(False, "skill gap confidence too low", min(validation.score, plugin.suggestion.gap.score))
        return CriticDecision(True, "approved for confirmed installation", min(1.0, validation.score + 0.05))


class SafeAutoInstaller:
    def __init__(self, plugins_root: Path = Path("skills"), state_root: Path = Path("state/plugin_installs"), guard: SafetyGuard | None = None) -> None:
        self.plugins_root = plugins_root
        self.state_root = state_root
        self.guard = guard or SafetyGuard()

    def install(
        self,
        plugin: GeneratedPlugin,
        validation: ValidationResult,
        critic: CriticDecision,
        confirmed: bool = False,
    ) -> InstallRecord:
        if not confirmed:
            raise PermissionError("installation requires explicit confirmation")
        if not validation.approved or not critic.approved:
            raise ValueError("plugin must pass validation and critic review before installation")
        name = plugin.suggestion.name
        backup_dir = self._backup_dir(name)
        files_written: list[str] = []
        manifest_path = self.guard.assert_inside(self.plugins_root, Path(f"{name}.plugin.json"))
        self._backup_existing(manifest_path, backup_dir)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(plugin.manifest, indent=2) + "\n", encoding="utf-8")
        files_written.append(manifest_path.as_posix())
        for relative, content in plugin.files.items():
            path = self.guard.assert_inside(self.plugins_root, Path(relative))
            self._backup_existing(path, backup_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            files_written.append(path.as_posix())
        record = InstallRecord(
            name,
            datetime.now(UTC).isoformat(),
            tuple(files_written),
            backup_dir.as_posix(),
            hashlib.sha256(json.dumps(plugin.manifest, sort_keys=True).encode("utf-8")).hexdigest(),
        )
        self._record(record)
        return record

    def rollback(self, record: InstallRecord) -> None:
        backup_dir = Path(record.backup_dir)
        for file_name in record.files:
            path = Path(file_name)
            backup = backup_dir / self._backup_name(path)
            if backup.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, path)
            elif path.exists():
                path.unlink()

    def _backup_existing(self, path: Path, backup_dir: Path) -> None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, backup_dir / self._backup_name(path))

    def _backup_dir(self, plugin_name: str) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return self.state_root / "backups" / f"{plugin_name}-{stamp}"

    def _backup_name(self, path: Path) -> str:
        return hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest() + ".bak"

    def _record(self, record: InstallRecord) -> None:
        log = self.state_root / "install_records.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8") if not log.exists() else None
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.__dict__) + "\n")


class SelfImprovingPluginSystem:
    def __init__(
        self,
        detector: SkillGapDetector | None = None,
        suggester: PluginSuggestionEngine | None = None,
        generator: PluginGenerator | None = None,
        validator: PluginValidator | None = None,
        critic: PluginCritic | None = None,
        installer: SafeAutoInstaller | None = None,
    ) -> None:
        self.detector = detector or SkillGapDetector()
        self.suggester = suggester or PluginSuggestionEngine()
        self.generator = generator or PluginGenerator()
        self.validator = validator or PluginValidator()
        self.critic = critic or PluginCritic()
        self.installer = installer or SafeAutoInstaller()

    def propose(self, signals: tuple[SkillSignal, ...]) -> tuple[tuple[GeneratedPlugin, ValidationResult, CriticDecision], ...]:
        proposals = []
        for suggestion in self.suggester.suggest(self.detector.detect(signals)):
            plugin = self.generator.generate(suggestion)
            validation = self.validator.validate(plugin)
            decision = self.critic.review(plugin, validation)
            proposals.append((plugin, validation, decision))
        return tuple(proposals)

    def install_best(self, signals: tuple[SkillSignal, ...], confirmed: bool = False) -> InstallRecord:
        approved = [
            item for item in self.propose(signals)
            if item[1].approved and item[2].approved
        ]
        if not approved:
            raise ValueError("no validated plugin proposal available")
        plugin, validation, decision = max(approved, key=lambda item: item[0].suggestion.gap.score)
        return self.installer.install(plugin, validation, decision, confirmed=confirmed)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:64] or "generated_plugin"
