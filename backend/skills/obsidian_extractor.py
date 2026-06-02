from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable

from backend.skills.parser import SkillRepository
from backend.vault.service import VaultService


SKILL_TAGS = "tags: [auto-generated, skill]"
DEFAULT_SKILLS_FOLDER = "skills"
MIN_PATTERN_COUNT = 2
MIN_USEFULNESS_SCORE = 0.68
SIMILARITY_THRESHOLD = 0.58
DUPLICATE_THRESHOLD = 0.74
MAX_SKILLS_PER_RUN = 5

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "when",
    "with",
}

PROCEDURE_HEADINGS = {
    "procedure",
    "process",
    "steps",
    "workflow",
    "runbook",
    "method",
    "instructions",
    "implementation",
}

ACTION_VERBS = {
    "add",
    "analyze",
    "apply",
    "build",
    "check",
    "classify",
    "compare",
    "create",
    "debug",
    "dedupe",
    "define",
    "detect",
    "extract",
    "find",
    "generate",
    "group",
    "identify",
    "implement",
    "index",
    "inspect",
    "load",
    "merge",
    "normalize",
    "parse",
    "rank",
    "read",
    "retrieve",
    "review",
    "route",
    "save",
    "score",
    "search",
    "summarize",
    "validate",
    "verify",
    "write",
}


@dataclass(frozen=True)
class ObsidianNote:
    path: str
    title: str
    content: str


@dataclass(frozen=True)
class ProcedureFragment:
    source_path: str
    title: str
    trigger_terms: tuple[str, ...]
    steps: tuple[str, ...]
    fallback: str
    signature: tuple[str, ...]


@dataclass(frozen=True)
class SkillDraft:
    name: str
    trigger: str
    context: str
    procedure: tuple[str, ...]
    fallback: str
    source_paths: tuple[str, ...]
    signature: tuple[str, ...]
    usefulness_score: float

    def markdown(self) -> str:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(self.procedure, start=1))
        return "\n".join(
            [
                f"# skill: {self.name}",
                "",
                SKILL_TAGS,
                "",
                "## trigger",
                self.trigger,
                "",
                "## context",
                self.context,
                "",
                "## procedure",
                steps,
                "",
                "## fallback",
                self.fallback,
                "",
            ]
        )


@dataclass(frozen=True)
class CriticReview:
    approved: bool
    score: float
    reason: str


@dataclass(frozen=True)
class SavedSkill:
    path: str
    draft: SkillDraft
    review: CriticReview


def extract_skills_from_obsidian(
    *,
    vault: VaultService | None = None,
    repository: SkillRepository | None = None,
    skills_folder: str = DEFAULT_SKILLS_FOLDER,
    minimum_count: int = MIN_PATTERN_COUNT,
    max_skills: int = MAX_SKILLS_PER_RUN,
) -> list[SavedSkill]:
    vault = vault or VaultService()
    repository = repository or SkillRepository()
    notes = load_obsidian_notes(vault)
    fragments = extract_procedure_fragments(notes)
    groups = group_similar_fragments(fragments, minimum_count=minimum_count)
    drafts = [merge_fragments_into_skill(group) for group in groups]
    drafts = deduplicate_skill_drafts(drafts, repository)

    saved: list[SavedSkill] = []
    for draft in sorted(drafts, key=lambda item: item.usefulness_score, reverse=True):
        if len(saved) >= max_skills:
            break
        review = validate_skill_usefulness(draft, repository)
        if not review.approved:
            continue
        path = write_skill_to_obsidian(vault, draft, skills_folder=skills_folder)
        saved.append(SavedSkill(path=path, draft=draft, review=review))
    return saved


def load_obsidian_notes(vault: VaultService) -> list[ObsidianNote]:
    notes: list[ObsidianNote] = []
    for item in vault.list_notes():
        path = item["path"]
        if Path(path).parts[:1] == (DEFAULT_SKILLS_FOLDER,):
            continue
        content = vault.read_note(path)
        notes.append(ObsidianNote(path=path, title=item.get("title") or Path(path).stem, content=content))
    return notes


def extract_procedure_fragments(notes: Iterable[ObsidianNote]) -> list[ProcedureFragment]:
    fragments: list[ProcedureFragment] = []
    for note in notes:
        blocks = extract_procedure_blocks(note.content)
        if not blocks:
            blocks = extract_action_blocks(note.content)
        for block in blocks:
            steps = tuple(generalize_step(step) for step in parse_steps(block))
            steps = tuple(step for step in steps if is_useful_step(step))
            if len(steps) < 2:
                continue
            terms = dominant_terms(" ".join([note.title, *steps]), limit=6)
            if len(terms) < 2:
                continue
            fragments.append(
                ProcedureFragment(
                    source_path=note.path,
                    title=note.title,
                    trigger_terms=tuple(terms[:4]),
                    steps=steps[:8],
                    fallback=derive_fallback(block),
                    signature=tuple(terms),
                )
            )
    return fragments


def extract_procedure_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    heading_re = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(markdown))
    for index, match in enumerate(matches):
        heading = normalize_heading(match.group(1))
        if heading not in PROCEDURE_HEADINGS:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def extract_action_blocks(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = strip_list_marker(line)
        if is_action_line(stripped):
            current.append(stripped)
            continue
        if len(current) >= 2:
            blocks.append(current)
        current = []

    if len(current) >= 2:
        blocks.append(current)

    return ["\n".join(block) for block in blocks]


def parse_steps(block: str) -> list[str]:
    steps: list[str] = []
    for line in block.splitlines():
        stripped = strip_list_marker(line)
        if not stripped or stripped.startswith("#"):
            continue
        if len(stripped.split()) < 3:
            continue
        steps.append(stripped)
    if steps:
        return steps
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", block) if len(sentence.split()) >= 5]


def group_similar_fragments(
    fragments: list[ProcedureFragment],
    *,
    minimum_count: int = MIN_PATTERN_COUNT,
) -> list[list[ProcedureFragment]]:
    groups: list[list[ProcedureFragment]] = []
    for fragment in fragments:
        for group in groups:
            if fragment_similarity(fragment, group[0]) >= SIMILARITY_THRESHOLD:
                group.append(fragment)
                break
        else:
            groups.append([fragment])

    return [
        group
        for group in groups
        if len({fragment.source_path for fragment in group}) >= minimum_count
    ]


def merge_fragments_into_skill(group: list[ProcedureFragment]) -> SkillDraft:
    all_terms = Counter(term for fragment in group for term in fragment.signature)
    signature = tuple(term for term, _ in all_terms.most_common(6))
    name = skill_name(signature)
    trigger_terms = ", ".join(signature[:4])
    procedure = merge_steps(fragment.steps for fragment in group)
    source_paths = tuple(sorted({fragment.source_path for fragment in group}))
    fallback = merge_fallbacks(fragment.fallback for fragment in group)
    usefulness = usefulness_score(source_count=len(source_paths), step_count=len(procedure), signature=signature)

    return SkillDraft(
        name=name,
        trigger=f"When a task repeatedly involves {trigger_terms}.",
        context=f"Solves recurring {trigger_terms} workflows found across Obsidian notes.",
        procedure=tuple(procedure),
        fallback=fallback,
        source_paths=source_paths,
        signature=signature,
        usefulness_score=usefulness,
    )


def deduplicate_skill_drafts(drafts: list[SkillDraft], repository: SkillRepository) -> list[SkillDraft]:
    existing_signatures = existing_skill_signatures(repository)
    accepted: list[SkillDraft] = []
    seen: list[set[str]] = []

    for draft in sorted(drafts, key=lambda item: item.usefulness_score, reverse=True):
        draft_terms = set(draft.signature)
        if any(jaccard(draft_terms, existing) >= DUPLICATE_THRESHOLD for existing in existing_signatures):
            continue
        if any(jaccard(draft_terms, terms) >= DUPLICATE_THRESHOLD for terms in seen):
            continue
        seen.append(draft_terms)
        accepted.append(draft)

    return accepted


def validate_skill_usefulness(draft: SkillDraft, repository: SkillRepository) -> CriticReview:
    if draft.usefulness_score < MIN_USEFULNESS_SCORE:
        return CriticReview(False, draft.usefulness_score, "pattern is not useful enough")
    if len(draft.source_paths) < MIN_PATTERN_COUNT:
        return CriticReview(False, draft.usefulness_score, "pattern does not appear multiple times")
    if len(draft.procedure) < 3:
        return CriticReview(False, draft.usefulness_score, "procedure is too shallow")
    if is_overfit(draft):
        return CriticReview(False, draft.usefulness_score, "draft overfits specific files, dates, or commands")
    if duplicates_existing_skill(draft, repository):
        return CriticReview(False, draft.usefulness_score, "duplicates an existing skill")
    return CriticReview(True, draft.usefulness_score, "approved")


def write_skill_to_obsidian(
    vault: VaultService,
    draft: SkillDraft,
    *,
    skills_folder: str = DEFAULT_SKILLS_FOLDER,
) -> str:
    slug = slugify(draft.name)
    note_path = f"{skills_folder.rstrip('/')}/{slug}.md"
    counter = 2
    existing_paths = {item["path"] for item in vault.list_notes()}

    while note_path in existing_paths:
        note_path = f"{skills_folder.rstrip('/')}/{slug}-{counter}.md"
        counter += 1

    vault.write_note(note_path, draft.markdown())
    return note_path


def example_skill_generation_flow(vault_path: Path) -> list[dict[str, object]]:
    vault = VaultService(vault_path=vault_path)
    saved = extract_skills_from_obsidian(vault=vault, repository=SkillRepository(roots=[vault_path / DEFAULT_SKILLS_FOLDER]))
    return [
        {
            "path": item.path,
            "name": item.draft.name,
            "score": item.review.score,
            "sources": list(item.draft.source_paths),
        }
        for item in saved
    ]


def strip_list_marker(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"^[-*+]\s+", "", stripped)
    stripped = re.sub(r"^\d+[.)]\s+", "", stripped)
    return stripped.strip()


def normalize_heading(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def is_action_line(text: str) -> bool:
    words = tokenize(text)
    return bool(words and words[0] in ACTION_VERBS and len(words) >= 3)


def is_useful_step(step: str) -> bool:
    terms = tokenize(step)
    return len(terms) >= 3 and not step.lower().startswith(("note:", "example:", "source:"))


def generalize_step(step: str) -> str:
    value = step.strip()
    value = re.sub(r"`[^`]+`", "<artifact>", value)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<date>", value)
    value = re.sub(r"\b\d+\b", "<number>", value)
    value = re.sub(r"(/[A-Za-z0-9_.-]+)+", "<path>", value)
    value = re.sub(r"\b[A-Za-z]:\\[^\s]+", "<path>", value)
    value = re.sub(r"\s+", " ", value)
    return value[:1].upper() + value[1:] if value else value


def derive_fallback(block: str) -> str:
    fallback = section_text(block, "fallback")
    if fallback:
        return generalize_step(fallback.splitlines()[0])
    return "If the procedure fails, retrieve more Obsidian context, check existing skills, and ask for clarification before saving changes."


def merge_steps(step_groups: Iterable[Iterable[str]]) -> list[str]:
    merged: list[str] = []
    seen: list[set[str]] = []
    for step in [step for group in step_groups for step in group]:
        terms = set(tokenize(step))
        if not terms:
            continue
        if any(jaccard(terms, existing) >= 0.68 for existing in seen):
            continue
        seen.append(terms)
        merged.append(step)
        if len(merged) >= 8:
            break
    return merged


def merge_fallbacks(fallbacks: Iterable[str]) -> str:
    fallback_list = [fallback for fallback in fallbacks if fallback]
    if not fallback_list:
        return "If the skill cannot be applied, stop and ask for clarification."
    return Counter(fallback_list).most_common(1)[0][0]


def section_text(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^#{1,6}\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^#{1,6}\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def dominant_terms(text: str, *, limit: int) -> list[str]:
    counts = Counter(tokenize(text))
    return [term for term, _ in counts.most_common(limit)]


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def fragment_similarity(left: ProcedureFragment, right: ProcedureFragment) -> float:
    signature_score = jaccard(set(left.signature), set(right.signature))
    step_score = jaccard(set(tokenize(" ".join(left.steps))), set(tokenize(" ".join(right.steps))))
    return (0.65 * signature_score) + (0.35 * step_score)


def usefulness_score(*, source_count: int, step_count: int, signature: tuple[str, ...]) -> float:
    source_score = min(1.0, source_count / 4)
    step_score = min(1.0, step_count / 5)
    abstraction_score = min(1.0, len(signature) / 5)
    return round((0.45 * source_score) + (0.35 * step_score) + (0.20 * abstraction_score), 6)


def existing_skill_signatures(repository: SkillRepository) -> list[set[str]]:
    signatures: list[set[str]] = []
    for skill in repository.list_skills():
        text = " ".join([skill.name, " ".join(skill.tags), skill.when_to_use, " ".join(skill.steps)])
        signatures.append(set(tokenize(text)))
    return signatures


def duplicates_existing_skill(draft: SkillDraft, repository: SkillRepository) -> bool:
    draft_terms = set(tokenize(" ".join([draft.name, draft.trigger, *draft.procedure])))
    return any(jaccard(draft_terms, existing) >= DUPLICATE_THRESHOLD for existing in existing_skill_signatures(repository))


def is_overfit(draft: SkillDraft) -> bool:
    text = " ".join([draft.name, draft.trigger, draft.context, *draft.procedure])
    placeholder_count = text.count("<path>") + text.count("<date>") + text.count("<number>") + text.count("<artifact>")
    proper_nouns = re.findall(r"\b[A-Z][a-z]+[A-Z][A-Za-z]*\b", text)
    return placeholder_count > 8 or len(proper_nouns) > 6


def skill_name(signature: tuple[str, ...]) -> str:
    terms = [term.replace("_", "-") for term in signature[:4]]
    return "-".join(terms) + "-workflow"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug or "generated-skill"


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def to_dict(saved: SavedSkill) -> dict[str, object]:
    return {
        "path": saved.path,
        "draft": asdict(saved.draft),
        "review": asdict(saved.review),
    }


__all__ = [
    "CriticReview",
    "ObsidianNote",
    "ProcedureFragment",
    "SavedSkill",
    "SkillDraft",
    "deduplicate_skill_drafts",
    "example_skill_generation_flow",
    "extract_procedure_fragments",
    "extract_skills_from_obsidian",
    "group_similar_fragments",
    "merge_fragments_into_skill",
    "to_dict",
    "validate_skill_usefulness",
    "write_skill_to_obsidian",
]
