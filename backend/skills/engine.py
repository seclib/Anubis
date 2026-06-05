from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any

from backend.agent.llm import LLM, OllamaLLM
from backend.core.config import settings
from rag.shared.backend_legacy.indexer import RagIndexer
from backend.skills.parser import SkillRepository
from backend.vault.service import VaultService


OBSERVATION_NOTE = "agent-runs/task-observations.md"
STOPWORDS = {
    "a",
    "an",
    "and",
    "build",
    "create",
    "for",
    "from",
    "implement",
    "into",
    "make",
    "please",
    "system",
    "task",
    "that",
    "the",
    "this",
    "to",
    "with",
}


@dataclass(frozen=True)
class TaskObservation:
    task: str
    timestamp: str
    outcome: str = ""

    def markdown_line(self) -> str:
        suffix = f" | outcome: {self.outcome}" if self.outcome else ""
        return f"- [{self.timestamp}] {self.task.strip()}{suffix}"


@dataclass(frozen=True)
class SkillPattern:
    signature: str
    keywords: list[str]
    tasks: list[str]


@dataclass(frozen=True)
class SkillProposal:
    name: str
    trigger: str
    procedure: list[str]
    source_tasks: list[str]
    confidence: float

    def markdown(self) -> str:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(self.procedure, start=1))
        sources = "\n".join(f"- {task}" for task in self.source_tasks)
        return f"""# skill: {self.name}
tags: [auto-generated, skill]

## trigger
{self.trigger}

## procedure
{steps}

## source tasks
{sources}
"""


@dataclass(frozen=True)
class CriticResult:
    approved: bool
    reason: str
    score: float


def _tokens(text: str) -> list[str]:
    words = [word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", text)]
    return [word for word in words if word not in STOPWORDS and len(word) > 2]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9_/-]+", "_", text.lower()).strip("_")
    return re.sub(r"_+", "_", slug) or "generated_skill"


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class SkillExtractor:
    def extract(self, observations: list[TaskObservation], minimum_count: int = 2) -> SkillPattern | None:
        buckets: dict[str, list[TaskObservation]] = {}
        for observation in observations:
            keywords = self.keywords(observation.task)
            if not keywords:
                continue
            signature = "_".join(keywords[:3])
            buckets.setdefault(signature, []).append(observation)

        repeated = [
            (signature, items)
            for signature, items in buckets.items()
            if len(items) >= minimum_count
        ]
        if not repeated:
            return None
        repeated.sort(key=lambda item: (len(item[1]), item[1][-1].timestamp), reverse=True)
        signature, items = repeated[0]
        tasks = [item.task for item in items[-6:]]
        return SkillPattern(signature=signature, keywords=signature.split("_"), tasks=tasks)

    def keywords(self, task: str) -> list[str]:
        counts = Counter(_tokens(task))
        return [word for word, _ in counts.most_common(5)]


class SkillCritic:
    def __init__(self, repository: SkillRepository | None = None) -> None:
        self.repository = repository or SkillRepository()

    def review(self, proposal: SkillProposal) -> CriticResult:
        if len(proposal.name) < 4:
            return CriticResult(False, "name is too short", 0.0)
        if proposal.confidence < 0.5:
            return CriticResult(False, "not enough repeated evidence", proposal.confidence)
        if len(proposal.procedure) < 3:
            return CriticResult(False, "procedure is too shallow", 0.2)
        proposal_terms = set(_tokens(" ".join([proposal.name, proposal.trigger, *proposal.procedure])))
        for skill in self.repository.list_skills():
            existing_terms = set(_tokens(" ".join([skill.name, skill.when_to_use, *skill.steps])))
            if skill.name.lower().replace("-", "_") == proposal.name.lower().replace("-", "_"):
                return CriticResult(False, "duplicate skill name", 0.0)
            if _overlap(proposal_terms, existing_terms) >= 0.72:
                return CriticResult(False, f"duplicates existing skill: {skill.name}", 0.1)
        if any(task.lower() == proposal.name.lower() for task in proposal.source_tasks):
            return CriticResult(False, "proposal overfits a single task", 0.2)
        return CriticResult(True, "approved", min(1.0, proposal.confidence + 0.2))


class SkillEngine:
    def __init__(
        self,
        llm: LLM | None = None,
        vault: VaultService | None = None,
        repository: SkillRepository | None = None,
        indexer: RagIndexer | None = None,
    ) -> None:
        self.llm = llm or OllamaLLM()
        self.vault = vault or VaultService()
        self.repository = repository or SkillRepository()
        self.indexer = indexer or RagIndexer()
        self.extractor = SkillExtractor()
        self.critic = SkillCritic(self.repository)

    def observe(self, task: str, outcome: str = "") -> dict[str, Any]:
        observation = TaskObservation(task=task, outcome=outcome, timestamp=datetime.now(UTC).isoformat())
        observed_path = self.store_observation(observation)
        result = self.improve_from_memory()
        return {"observed": observed_path, **result}

    def improve_from_memory(self, minimum_count: int = 2) -> dict[str, Any]:
        observations = self.load_observations()
        pattern = self.extractor.extract(observations, minimum_count=minimum_count)
        if not pattern:
            return {"skill_saved": None, "critic": asdict(CriticResult(False, "no repeated pattern", 0.0))}
        proposal = self.propose(pattern)
        critic = self.critic.review(proposal)
        if not critic.approved:
            return {"skill_saved": None, "proposal": asdict(proposal), "critic": asdict(critic)}
        saved_path = self.save(proposal)
        return {"skill_saved": saved_path, "proposal": asdict(proposal), "critic": asdict(critic)}

    def store_observation(self, observation: TaskObservation) -> str:
        try:
            existing = self.vault.read_note(OBSERVATION_NOTE)
        except FileNotFoundError:
            existing = "# Task observations\n"
        self.vault.write_note(OBSERVATION_NOTE, f"{existing.rstrip()}\n{observation.markdown_line()}\n")
        return OBSERVATION_NOTE

    def load_observations(self) -> list[TaskObservation]:
        try:
            text = self.vault.read_note(OBSERVATION_NOTE)
        except FileNotFoundError:
            return []
        observations = []
        for line in text.splitlines():
            match = re.match(r"^-\s+\[(?P<timestamp>[^\]]+)\]\s+(?P<body>.+)$", line.strip())
            if not match:
                continue
            body = match.group("body")
            task, _, outcome = body.partition(" | outcome: ")
            observations.append(TaskObservation(task=task.strip(), timestamp=match.group("timestamp"), outcome=outcome.strip()))
        return observations

    def propose(self, pattern: SkillPattern) -> SkillProposal:
        name = f"{pattern.signature}_workflow"
        procedure = self._llm_procedure(pattern) or self._default_procedure(pattern)
        confidence = min(1.0, len(pattern.tasks) / 4)
        return SkillProposal(
            name=name,
            trigger=f"When a task involves {', '.join(pattern.keywords)} in a similar workflow.",
            procedure=procedure,
            source_tasks=pattern.tasks,
            confidence=confidence,
        )

    def save(self, proposal: SkillProposal) -> str:
        settings.skills_path.mkdir(parents=True, exist_ok=True)
        slug = _slug(proposal.name)
        path = settings.skills_path / f"{slug}.md"
        counter = 2
        while path.exists():
            path = settings.skills_path / f"{slug}_{counter}.md"
            counter += 1
        rel_path = path.resolve().relative_to(settings.vault_path.resolve()).as_posix()
        self.vault.write_note(rel_path, proposal.markdown())
        self.indexer.index_note(rel_path)
        return rel_path

    def _llm_procedure(self, pattern: SkillPattern) -> list[str]:
        prompt = {
            "task": "generalize repeated tasks into a reusable skill procedure",
            "keywords": pattern.keywords,
            "source_tasks": pattern.tasks,
            "rules": ["generalize", "avoid overfitting", "return JSON array of strings only"],
        }
        response = self.llm.generate(json.dumps(prompt, ensure_ascii=False))
        if response.startswith("```"):
            lines = response.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response = "\n".join(lines)
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        procedure = [str(item).strip() for item in parsed if str(item).strip()]
        return procedure[:8]

    def _default_procedure(self, pattern: SkillPattern) -> list[str]:
        phrase = " ".join(pattern.keywords)
        return [
            f"Recognize the recurring {phrase} task pattern.",
            "Retrieve relevant vault notes, prior runs, and existing skills before acting.",
            "Apply the smallest safe sequence of steps that solves the generalized pattern.",
            "Validate the result against the requested outcome.",
            "Store any durable lesson or refined procedure back into the vault.",
        ]
