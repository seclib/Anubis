from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

from rag.discovery.schema import DiscoveryEntry, SEARCH_ENGINES


class DiscoveryParser:
    def parse_path(self, path: str | Path) -> list[DiscoveryEntry]:
        root = Path(path)
        if root.is_file():
            return self.parse_file(root)
        entries: list[DiscoveryEntry] = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix == ".csv":
                entries.extend(self.parse_csv(file_path))
            elif suffix in {".json", ".jsonl"}:
                entries.extend(self.parse_json(file_path))
            elif suffix in {".txt", ".md", ".lst"}:
                entries.extend(self.parse_lines(file_path))
        return self._dedupe(entries)

    def parse_file(self, path: Path) -> list[DiscoveryEntry]:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self.parse_csv(path)
        if suffix in {".json", ".jsonl"}:
            return self.parse_json(path)
        return self.parse_lines(path)

    def parse_csv(self, path: Path) -> list[DiscoveryEntry]:
        entries = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                entries.append(self._entry_from_mapping(row, path))
        return self._dedupe(entries)

    def parse_json(self, path: Path) -> list[DiscoveryEntry]:
        if path.suffix.lower() == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        else:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            rows = payload if isinstance(payload, list) else payload.get("entries") or payload.get("dorks") or payload.get("queries") or [payload]
        return self._dedupe(self._entry_from_mapping(row, path) for row in rows if isinstance(row, dict))

    def parse_lines(self, path: Path) -> list[DiscoveryEntry]:
        entries = []
        category = self._category_from_path(path)
        source = self._source_from_path(path)
        engine = self._engine_from_text(f"{path} {source}")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                title, query, description, tags = self._parse_line(line)
                entries.append(
                    DiscoveryEntry(
                        title=title or f"{source} query {index}",
                        source=source,
                        category=category,
                        query=query,
                        description=description,
                        tags=tuple(tags),
                        search_engine=engine or self._engine_from_text(query),
                        source_uri=f"{path.as_posix()}:{index}",
                        raw={"line": line},
                    )
                )
        return self._dedupe(entries)

    def _entry_from_mapping(self, row: dict[str, Any], path: Path) -> DiscoveryEntry:
        normalized = {str(key).strip().lower().replace(" ", "_"): value for key, value in row.items()}
        query = str(
            normalized.get("query")
            or normalized.get("dork")
            or normalized.get("search")
            or normalized.get("google_dork")
            or normalized.get("shodan_query")
            or normalized.get("censys_query")
            or normalized.get("fofa_query")
            or ""
        ).strip()
        title = str(normalized.get("title") or normalized.get("name") or normalized.get("description") or query[:80] or path.stem).strip()
        source = str(normalized.get("source") or self._source_from_path(path)).strip()
        category = str(normalized.get("category") or normalized.get("type") or self._category_from_path(path)).strip()
        description = str(normalized.get("description") or normalized.get("notes") or normalized.get("comment") or "").strip()
        tags = self._split_tags(normalized.get("tags") or normalized.get("tag") or normalized.get("labels") or "")
        engine = str(normalized.get("search_engine") or normalized.get("engine") or self._engine_from_text(f"{source} {path} {query}")).strip()
        return DiscoveryEntry(
            title=title,
            source=source,
            category=category,
            query=query,
            description=description,
            tags=tuple(tags),
            search_engine=engine,
            source_uri=str(normalized.get("source_uri") or path.as_posix()),
            raw=row,
        )

    def _parse_line(self, line: str) -> tuple[str, str, str, list[str]]:
        if "\t" in line:
            parts = [part.strip() for part in line.split("\t")]
        elif "|" in line:
            parts = [part.strip() for part in line.split("|")]
        else:
            parts = [line]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2], self._split_tags(parts[3] if len(parts) > 3 else "")
        if len(parts) == 2:
            return parts[0], parts[1], "", []
        return "", parts[0], "", []

    def _split_tags(self, value: Any) -> list[str]:
        if isinstance(value, list):
            raw = [str(item) for item in value]
        else:
            raw = re.split(r"[,;|]", str(value or ""))
        return sorted({item.strip() for item in raw if item and item.strip()})

    def _source_from_path(self, path: Path) -> str:
        text = path.as_posix().lower()
        if "ghdb" in text or "google-hacking" in text:
            return "GHDB"
        if "github" in text:
            return "GitHub Dorks"
        if "gitlab" in text:
            return "GitLab Dorks"
        if "shodan" in text:
            return "Shodan"
        if "censys" in text:
            return "Censys"
        if "fofa" in text:
            return "FOFA"
        if "google" in text:
            return "Google Dorks"
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _category_from_path(self, path: Path) -> str:
        parent = path.parent.name
        if parent and parent not in {".", ""}:
            return parent.replace("_", " ").replace("-", " ").strip().lower()
        return "uncategorized"

    def _engine_from_text(self, text: str) -> str:
        lowered = text.lower()
        for engine in SEARCH_ENGINES:
            if engine in lowered:
                return engine
        if any(token in lowered for token in ("site:", "intitle:", "inurl:", "filetype:", "ext:")):
            return "google"
        return ""

    def _dedupe(self, entries: Iterable[DiscoveryEntry]) -> list[DiscoveryEntry]:
        deduped: dict[str, DiscoveryEntry] = {}
        for entry in entries:
            if not entry.query:
                continue
            key = f"{entry.search_engine}:{entry.category}:{entry.query}".lower()
            existing = deduped.get(key)
            if existing is None or len(entry.description) > len(existing.description):
                deduped[key] = entry
        return list(deduped.values())
