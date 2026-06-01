"""Knowledge maintenance service for the Obsidian vault."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge.gaps import KnowledgeGapDetector
from knowledge.ingestion import get_obsidian_ingestion_pipeline
from knowledge.merge import NoteMergeService
from memory import hermes, vector


ENTITY_PATTERN = re.compile(r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|YARA|Sigma|Mimikatz|Metasploit|Nmap|Burp Suite)\b", re.I)


@dataclass
class NoteRecord:
    path: Path
    text: str
    title: str
    content_hash: str


class KnowledgeService:
    def __init__(self) -> None:
        self.gaps = KnowledgeGapDetector()
        self.merger = NoteMergeService()

    def vault_health(self) -> dict[str, Any]:
        notes = self._notes()
        duplicates = self.find_duplicates(notes=notes)
        stale = self.find_stale_notes(notes=notes)
        gaps = self.detect_gaps(notes=notes)
        orphans = [self._display(note.path) for note in notes if "[[" not in note.text and len(note.text) > 500]
        return {
            "notes": len(notes),
            "duplicate_candidates": len(duplicates),
            "stale_notes": len(stale),
            "knowledge_gaps": len(gaps),
            "orphan_notes": len(orphans),
            "vault": self._display(hermes.obsidian_vault_path(create=True)),
        }

    def maintain(self, *, apply: bool = True) -> dict[str, Any]:
        notes = self._notes()
        duplicates = self.find_duplicates(notes=notes)
        stale = self.find_stale_notes(notes=notes)
        backlink_updates = self.create_backlinks(notes=notes, apply=apply)
        tag_updates = self.ensure_tags(notes=notes, apply=apply)
        gaps = self.detect_gaps(notes=notes)
        merges = self.merge_duplicates(duplicates, apply=apply)
        index = self.ingest_vault(force=False, index_qdrant=True) if apply else {"status": "dry-run"}
        report = {
            "applied": apply,
            "duplicates": duplicates,
            "merges": merges,
            "stale": stale,
            "gaps": gaps,
            "backlink_updates": backlink_updates,
            "tag_updates": tag_updates,
            "index": index,
        }
        if apply:
            self._write_maintenance_report(report)
        return report

    def ingest_vault(
        self,
        *,
        limit: int | None = None,
        force: bool = False,
        index_qdrant: bool = True,
    ) -> dict[str, Any]:
        return get_obsidian_ingestion_pipeline().ingest_vault(
            limit=limit,
            force=force,
            index_qdrant=index_qdrant,
        )

    def find_duplicates(self, notes: list[NoteRecord] | None = None) -> list[dict[str, Any]]:
        notes = notes or self._notes()
        by_hash: dict[str, list[NoteRecord]] = {}
        for note in notes:
            by_hash.setdefault(note.content_hash, []).append(note)
        duplicates: list[dict[str, Any]] = []
        for digest, group in by_hash.items():
            if len(group) > 1:
                duplicates.append(
                    {
                        "reason": "exact_content_hash",
                        "hash": digest,
                        "notes": [self._display(note.path) for note in group],
                    }
                )
        title_seen: dict[str, Path] = {}
        for note in notes:
            key = re.sub(r"[^a-z0-9]+", "-", note.title.lower()).strip("-")
            if key and key in title_seen:
                duplicates.append(
                    {
                        "reason": "similar_title",
                        "notes": [self._display(title_seen[key]), self._display(note.path)],
                    }
                )
            elif key:
                title_seen[key] = note.path
        return duplicates[:100]

    def merge_duplicates(self, duplicate_groups: list[dict[str, Any]], *, apply: bool = False) -> list[dict[str, Any]]:
        exact_groups = [group for group in duplicate_groups if group.get("reason") == "exact_content_hash"]
        return self.merger.merge_exact_duplicates(exact_groups, apply=apply)

    def detect_gaps(self, notes: list[NoteRecord] | None = None) -> list[dict[str, Any]]:
        return self.gaps.detect(notes or self._notes())

    def find_stale_notes(self, notes: list[NoteRecord] | None = None, days: int = 90) -> list[dict[str, Any]]:
        notes = notes or self._notes()
        now = datetime.now(timezone.utc).timestamp()
        stale: list[dict[str, Any]] = []
        for note in notes:
            try:
                age_days = (now - note.path.stat().st_mtime) / 86400
            except OSError:
                continue
            if age_days >= days and any(term in note.text.lower() for term in ("cve", "exploit", "malware", "github", "advisory")):
                stale.append({"note": self._display(note.path), "age_days": round(age_days, 1)})
        return stale[:100]

    def create_backlinks(self, notes: list[NoteRecord] | None = None, *, apply: bool = True) -> list[dict[str, Any]]:
        notes = notes or self._notes()
        titles = {note.title.lower(): note.title for note in notes if note.title}
        updates: list[dict[str, Any]] = []
        for note in notes:
            text = note.text
            changed = text
            for entity in set(match.group(0) for match in ENTITY_PATTERN.finditer(text)):
                if f"[[{entity}]]" in changed:
                    continue
                canonical = titles.get(entity.lower(), entity)
                changed = re.sub(rf"\b{re.escape(entity)}\b", f"[[{canonical}]]", changed, count=1)
            if changed != text:
                updates.append({"note": self._display(note.path), "action": "backlinks_added"})
                if apply:
                    note.path.write_text(changed, encoding="utf-8")
        return updates[:100]

    def ensure_tags(self, notes: list[NoteRecord] | None = None, *, apply: bool = True) -> list[dict[str, Any]]:
        notes = notes or self._notes()
        updates: list[dict[str, Any]] = []
        for note in notes:
            lower = note.text.lower()
            tags = []
            if "cve" in lower or "vulnerability" in lower:
                tags.append("domain/vulnerability")
            if "malware" in lower or "yara" in lower:
                tags.append("domain/malware")
            if "osint" in lower or "recon" in lower:
                tags.append("domain/osint")
            if "github" in lower or "python" in lower:
                tags.append("domain/programming")
            if not tags or "tags:" in note.text[:800]:
                continue
            frontmatter = "---\ntype: knowledge\nstatus: active\ntags:\n" + "".join(f"  - {tag}\n" for tag in sorted(set(tags))) + "---\n\n"
            updates.append({"note": self._display(note.path), "tags": sorted(set(tags))})
            if apply:
                note.path.write_text(frontmatter + note.text, encoding="utf-8")
        return updates[:100]

    def _notes(self) -> list[NoteRecord]:
        root = hermes.obsidian_vault_path(create=True)
        records: list[NoteRecord] = []
        for path in sorted(root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not text.strip():
                continue
            title = self._title(path, text)
            records.append(NoteRecord(path=path, text=text, title=title, content_hash=vector._content_hash(text)))
        return records

    def _title(self, path: Path, text: str) -> str:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()[:160]
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip()[:160]
        return path.stem

    def _display(self, path: Path) -> str:
        try:
            from core.workspace import relative_to_workspace

            return relative_to_workspace(path)
        except Exception:
            return str(path)

    def _write_maintenance_report(self, report: dict[str, Any]) -> None:
        title = f"Knowledge Maintenance {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
        body = (
            f"# {title}\n\n"
            "## Summary\n\n"
            f"- Duplicate candidates: {len(report.get('duplicates', []))}\n"
            f"- Merges: {len(report.get('merges', []))}\n"
            f"- Stale notes: {len(report.get('stale', []))}\n"
            f"- Knowledge gaps: {len(report.get('gaps', []))}\n"
            f"- Backlink updates: {len(report.get('backlink_updates', []))}\n"
            f"- Tag updates: {len(report.get('tag_updates', []))}\n"
        )
        hermes.write_obsidian_note(title, body, folder="70-maintenance/audit-logs")


_SERVICE: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = KnowledgeService()
    return _SERVICE


__all__ = ["KnowledgeService", "get_knowledge_service"]
