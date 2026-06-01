"""Note merge helpers for self-healing Obsidian maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory import hermes, vector


class NoteMergeService:
    def merge_exact_duplicates(self, duplicate_groups: list[dict[str, Any]], *, apply: bool = False) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        vault = hermes.obsidian_vault_path(create=True)
        archive = vault / "90-archive" / "merged"
        if apply:
            archive.mkdir(parents=True, exist_ok=True)
        for group in duplicate_groups:
            notes = [vault / str(path) for path in group.get("notes", [])]
            existing = [path for path in notes if path.exists()]
            if len(existing) < 2:
                continue
            canonical = sorted(existing, key=lambda path: (len(path.read_text(encoding="utf-8", errors="ignore")), str(path)), reverse=True)[0]
            for duplicate in existing:
                if duplicate == canonical:
                    continue
                action = {
                    "canonical": self._display(canonical),
                    "duplicate": self._display(duplicate),
                    "reason": group.get("reason", "duplicate"),
                }
                if apply:
                    target = archive / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{duplicate.name}"
                    duplicate.rename(target)
                    canonical_text = canonical.read_text(encoding="utf-8", errors="ignore")
                    marker = f"\n\n## Merged Notes\n\n- Archived duplicate: [[{target.stem}]]\n"
                    if "## Merged Notes" not in canonical_text:
                        canonical.write_text(canonical_text.rstrip() + marker, encoding="utf-8")
                    action["archived_to"] = self._display(target)
                actions.append(action)
        return actions[:100]

    def _display(self, path: Path) -> str:
        try:
            return str(path.relative_to(hermes.obsidian_vault_path(create=True)))
        except Exception:
            return str(path)


__all__ = ["NoteMergeService"]

