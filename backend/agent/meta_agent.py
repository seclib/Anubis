from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any, Literal

from backend.agent.llm import LLM, OllamaLLM
from backend.rag.indexer import RagIndexer
from backend.skills.engine import SkillEngine, SkillProposal
from backend.skills.parser import SkillRepository
from backend.vault.service import VaultService


ImprovementKind = Literal["system_prompt", "skill", "agent_loop"]


@dataclass(frozen=True)
class RunTrace:
    path: str
    task: str
    answer: str
    actions: list[dict[str, Any]]
    skills: list[str]


@dataclass(frozen=True)
class ImprovementSignal:
    kind: ImprovementKind
    title: str
    evidence: list[str]
    severity: int


@dataclass(frozen=True)
class ImprovementProposal:
    kind: ImprovementKind
    title: str
    rationale: str
    change: str
    evidence: list[str]

    def markdown(self) -> str:
        evidence = "\n".join(f"- {item}" for item in self.evidence) or "- none"
        return f"""# meta-improvement: {self.title}

kind: {self.kind}

## rationale
{self.rationale}

## proposed change
{self.change}

## evidence
{evidence}
"""


@dataclass(frozen=True)
class MetaCritique:
    approved: bool
    reason: str
    score: float


def _section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def _tokens(text: str) -> list[str]:
    stop = {"and", "for", "from", "into", "that", "the", "this", "with", "task", "user"}
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", text.lower())
    return [word for word in words if word not in stop and len(word) > 2]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", slug) or "proposal"


class ImprovementDetector:
    def detect(self, traces: list[RunTrace]) -> list[ImprovementSignal]:
        signals: list[ImprovementSignal] = []
        signals.extend(self._failure_signals(traces))
        signals.extend(self._prompt_signals(traces))
        signals.extend(self._skill_gap_signals(traces))
        signals.extend(self._loop_signals(traces))
        signals.sort(key=lambda signal: signal.severity, reverse=True)
        return signals

    def _failure_signals(self, traces: list[RunTrace]) -> list[ImprovementSignal]:
        failed = [
            trace
            for trace in traces
            if any(action.get("ok") is False for action in trace.actions)
            or "could not find anything relevant" in trace.answer.lower()
        ]
        if len(failed) < 2:
            return []
        return [
            ImprovementSignal(
                kind="agent_loop",
                title="Add explicit failure recovery branch",
                evidence=[trace.path for trace in failed[-5:]],
                severity=min(10, 4 + len(failed)),
            )
        ]

    def _prompt_signals(self, traces: list[RunTrace]) -> list[ImprovementSignal]:
        weak_answers = [
            trace
            for trace in traces
            if len(trace.answer.strip()) < 80 or "no matching skill found" in trace.answer.lower()
        ]
        if len(weak_answers) < 2:
            return []
        return [
            ImprovementSignal(
                kind="system_prompt",
                title="Require compact evidence-backed final answers",
                evidence=[trace.path for trace in weak_answers[-5:]],
                severity=min(9, 3 + len(weak_answers)),
            )
        ]

    def _skill_gap_signals(self, traces: list[RunTrace]) -> list[ImprovementSignal]:
        no_skill = [trace for trace in traces if not trace.skills or trace.skills == ["none"]]
        if len(no_skill) < 2:
            return []
        common = Counter(token for trace in no_skill for token in _tokens(trace.task)).most_common(3)
        topic = " ".join(word for word, _ in common) or "missing workflow"
        return [
            ImprovementSignal(
                kind="skill",
                title=f"Create reusable skill for {topic}",
                evidence=[trace.path for trace in no_skill[-5:]],
                severity=min(8, 3 + len(no_skill)),
            )
        ]

    def _loop_signals(self, traces: list[RunTrace]) -> list[ImprovementSignal]:
        repeated_actions = []
        for trace in traces:
            tools = [str(action.get("tool", "")) for action in trace.actions]
            if len(tools) >= 2 and len(set(tools)) < len(tools):
                repeated_actions.append(trace)
        if len(repeated_actions) < 2:
            return []
        return [
            ImprovementSignal(
                kind="agent_loop",
                title="Avoid repeated identical tool calls",
                evidence=[trace.path for trace in repeated_actions[-5:]],
                severity=min(8, 3 + len(repeated_actions)),
            )
        ]


class MetaCritic:
    def __init__(self, repository: SkillRepository | None = None) -> None:
        self.repository = repository or SkillRepository()

    def review(self, proposal: ImprovementProposal) -> MetaCritique:
        if len(proposal.evidence) < 2:
            return MetaCritique(False, "not enough evidence", 0.2)
        if len(proposal.change.strip()) < 40:
            return MetaCritique(False, "change is too vague", 0.3)
        if proposal.kind == "skill" and self._duplicates_skill(proposal):
            return MetaCritique(False, "duplicates existing skill", 0.1)
        if any(word in proposal.change.lower() for word in ["overwrite", "delete all", "disable validation"]):
            return MetaCritique(False, "unsafe proposed change", 0.0)
        return MetaCritique(True, "approved", min(1.0, 0.5 + len(proposal.evidence) / 10))

    def _duplicates_skill(self, proposal: ImprovementProposal) -> bool:
        proposal_terms = set(_tokens(proposal.title + " " + proposal.change))
        for skill in self.repository.list_skills():
            skill_terms = set(_tokens(skill.name + " " + skill.when_to_use + " " + " ".join(skill.steps)))
            if proposal_terms and len(proposal_terms & skill_terms) / len(proposal_terms | skill_terms) >= 0.65:
                return True
        return False


class MetaAgent:
    def __init__(
        self,
        llm: LLM | None = None,
        vault: VaultService | None = None,
        indexer: RagIndexer | None = None,
        skill_engine: SkillEngine | None = None,
    ) -> None:
        self.llm = llm or OllamaLLM()
        self.vault = vault or VaultService()
        self.indexer = indexer or RagIndexer()
        self.skill_engine = skill_engine or SkillEngine(llm=self.llm, vault=self.vault, indexer=self.indexer)
        self.detector = ImprovementDetector()
        self.critic = MetaCritic()

    def analyze(self, limit: int = 30, auto_skill: bool = False) -> dict[str, Any]:
        traces = self.load_traces(limit=limit)
        signals = self.detector.detect(traces)
        reviewed = []
        saved = []
        generated_skills = []
        for signal in signals:
            proposal = self.propose(signal, traces)
            critique = self.critic.review(proposal)
            reviewed.append({"signal": asdict(signal), "proposal": asdict(proposal), "critic": asdict(critique)})
            if not critique.approved:
                continue
            saved.append(self.save_proposal(proposal, critique))
            if auto_skill and proposal.kind == "skill":
                generated = self.generate_skill_from_proposal(proposal)
                if generated:
                    generated_skills.append(generated)
        return {
            "traces_analyzed": len(traces),
            "signals": [asdict(signal) for signal in signals],
            "reviewed": reviewed,
            "saved_proposals": saved,
            "generated_skills": generated_skills,
        }

    def load_traces(self, limit: int = 30) -> list[RunTrace]:
        notes = [
            note
            for note in self.vault.list_notes()
            if note["path"].startswith("agent-runs/") and note["path"].endswith(".md")
        ][-limit:]
        traces = []
        for note in notes:
            text = self.vault.read_note(note["path"])
            traces.append(
                RunTrace(
                    path=note["path"],
                    task=_section(text, "task"),
                    answer=_section(text, "answer"),
                    skills=self._list_section(text, "retrieved skills"),
                    actions=self._actions(text),
                )
            )
        return traces

    def propose(self, signal: ImprovementSignal, traces: list[RunTrace]) -> ImprovementProposal:
        evidence_tasks = [trace.task for trace in traces if trace.path in signal.evidence and trace.task]
        llm_change = self._llm_change(signal, evidence_tasks)
        change = llm_change or self._default_change(signal, evidence_tasks)
        return ImprovementProposal(
            kind=signal.kind,
            title=signal.title,
            rationale=f"Detected {len(signal.evidence)} recurring trace(s) with severity {signal.severity}.",
            change=change,
            evidence=signal.evidence,
        )

    def save_proposal(self, proposal: ImprovementProposal, critique: MetaCritique) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = f"meta-agent/proposals/{timestamp}-{_slug(proposal.title)}.md"
        content = proposal.markdown() + "\n## critic\n" + json.dumps(asdict(critique), indent=2) + "\n"
        self.vault.write_note(path, content)
        self.indexer.index_note(path)
        return path

    def generate_skill_from_proposal(self, proposal: ImprovementProposal) -> str | None:
        if proposal.kind != "skill":
            return None
        skill = SkillProposal(
            name=_slug(proposal.title).replace("-", "_"),
            trigger=proposal.rationale,
            procedure=[line.strip("- ").strip() for line in proposal.change.splitlines() if line.strip()][:6],
            source_tasks=proposal.evidence,
            confidence=0.7,
        )
        critique = self.skill_engine.critic.review(skill)
        if not critique.approved:
            return None
        return self.skill_engine.save(skill)

    def _llm_change(self, signal: ImprovementSignal, tasks: list[str]) -> str:
        prompt = {
            "role": "meta-agent",
            "signal": asdict(signal),
            "tasks": tasks,
            "rules": [
                "propose one minimal interpretable improvement",
                "do not modify files directly",
                "return plain text only",
            ],
        }
        response = self.llm.generate(json.dumps(prompt, ensure_ascii=False)).strip()
        if response.startswith("{") or response.startswith("[") or response.startswith("[LLM ERROR]"):
            return ""
        return response[:2000]

    def _default_change(self, signal: ImprovementSignal, tasks: list[str]) -> str:
        if signal.kind == "system_prompt":
            return (
                "Add a prompt rule: before finalizing, cite the specific retrieved note or skill used, "
                "state the next concrete action, and avoid empty generic answers when context is weak."
            )
        if signal.kind == "skill":
            topic = ", ".join(_tokens(" ".join(tasks))[:4]) or "the repeated workflow"
            return "\n".join(
                [
                    f"Recognize tasks involving {topic}.",
                    "Retrieve matching memory and existing skills.",
                    "Apply the smallest repeatable procedure.",
                    "Validate the result and record reusable learning.",
                ]
            )
        return (
            "Add a loop guard: when a step fails or repeats the same tool call, summarize the failure, "
            "retrieve fresh context, and re-plan once before continuing."
        )

    def _list_section(self, markdown: str, heading: str) -> list[str]:
        section = _section(markdown, heading)
        values = [line.strip("- ").strip() for line in section.splitlines() if line.strip()]
        return values or []

    def _actions(self, markdown: str) -> list[dict[str, Any]]:
        section = _section(markdown, "actions")
        match = re.search(r"```json\s*(.*?)```", section, re.DOTALL)
        raw = match.group(1) if match else section
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
