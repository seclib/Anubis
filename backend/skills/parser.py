from dataclasses import dataclass
from pathlib import Path
import re

from backend.core.config import settings
from backend.core.paths import ensure_inside


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    path: str
    tags: list[str]
    when_to_use: str
    steps: list[str]
    tools: str
    markdown: str

    def as_context(self) -> str:
        parts = [
            f"# skill: {self.name}",
            f"path: {self.path}",
            f"tags: {', '.join(self.tags) if self.tags else 'none'}",
        ]
        if self.when_to_use:
            parts.extend(["", "## trigger", self.when_to_use])
        if self.steps:
            parts.extend(["", "## steps"])
            parts.extend(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))
        if self.tools:
            parts.extend(["", "## tools", self.tools])
        return "\n".join(parts).strip()


def _parse_frontmatter(markdown: str) -> tuple[dict[str, object], str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown
    metadata: dict[str, object] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            metadata[key] = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        else:
            metadata[key] = value.strip("'\"")
    return metadata, markdown[match.end() :]


def _section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", markdown[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(markdown)
    return markdown[match.end() : end].strip()


def _title_name(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title.lower().startswith("skill:"):
                return title.split(":", 1)[1].strip()
            return title
    return fallback


def _parse_tags(metadata: dict[str, object], markdown: str) -> list[str]:
    raw = metadata.get("tags", [])
    if isinstance(raw, str):
        tags = [item.strip() for item in raw.strip("[]").split(",") if item.strip()]
    elif isinstance(raw, list):
        tags = [str(item).strip() for item in raw if str(item).strip()]
    else:
        tags = []
    if tags:
        return tags
    for line in markdown.splitlines():
        if line.lower().startswith("tags:"):
            return [item.strip().strip("[]") for item in line.split(":", 1)[1].split(",") if item.strip()]
    return []


def _parse_steps(markdown: str) -> list[str]:
    steps_text = _section(markdown, "steps") or _section(markdown, "procedure")
    steps: list[str] = []
    for line in steps_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = re.sub(r"^\d+[.)]\s+", "", stripped)
        steps.append(stripped)
    return steps


def parse_skill_markdown(path: str, markdown: str) -> Skill:
    metadata, body = _parse_frontmatter(markdown)
    name = str(metadata.get("name") or _title_name(body, Path(path).stem)).strip()
    return Skill(
        name=name,
        path=path,
        tags=_parse_tags(metadata, body),
        when_to_use=_section(body, "when to use") or _section(body, "trigger"),
        steps=_parse_steps(body),
        tools=_section(body, "tools") or _section(body, "script") or _section(body, "tool instructions"),
        markdown=markdown,
    )


class SkillRepository:
    def __init__(self, roots: list[Path] | None = None) -> None:
        self.roots = roots or self._default_roots()

    def _default_roots(self) -> list[Path]:
        configured = settings.skills_path
        roots = [configured]
        vault_skills = settings.vault_path / "skills"
        if vault_skills not in roots:
            roots.append(vault_skills)
        legacy = Path(".agents/skills")
        if legacy not in roots:
            roots.append(legacy)
        return roots

    def list_skills(self) -> list[Skill]:
        skills: list[Skill] = []
        seen: set[Path] = set()
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.md")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                rel = self._context_path(path, root)
                skills.append(parse_skill_markdown(rel, path.read_text(encoding="utf-8")))
        return skills

    def _context_path(self, path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(settings.vault_path.resolve()).as_posix()
        except ValueError:
            return path.relative_to(root).as_posix()

    def search(self, query: str, limit: int = 4) -> list[Skill]:
        query_terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_/-]+", query)}
        scored: list[tuple[int, Skill]] = []
        for skill in self.list_skills():
            haystack = " ".join([skill.name, " ".join(skill.tags), skill.when_to_use, " ".join(skill.steps)]).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score or "skill" in skill.tags:
                scored.append((score, skill))
        scored.sort(key=lambda item: (item[0], item[1].name.lower()), reverse=True)
        return [skill for _, skill in scored[:limit]]

    def read(self, root: Path, note_path: str) -> str:
        path = ensure_inside(root, Path(note_path))
        return path.read_text(encoding="utf-8")
