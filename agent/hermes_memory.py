"""Hermes long-term memory backed by JSON, Obsidian notes, and vector recall."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from agent import vector_memory
from config import (
    HERMES_MEMORY_ENABLED,
    HERMES_MEMORY_BACKEND,
    HERMES_MEMORY_FILE,
    OBSIDIAN_DAILY_MEMORY_DIR,
    OBSIDIAN_VAULT_PATH,
    QDRANT_COLLECTION,
    QDRANT_URL,
)
from tools.sandbox import relative_to_workspace, resolve_workspace_path, workspace_root

MAX_NOTE_BYTES = 256_000
MAX_RECALL_TEXT = 1400


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_path() -> Path:
    path = HERMES_MEMORY_FILE
    if not path.is_absolute():
        path = workspace_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return resolve_workspace_path(path, must_exist=False)


def obsidian_vault_path(create: bool = True) -> Path:
    path = OBSIDIAN_VAULT_PATH
    safe_path = (
        path.expanduser().resolve(strict=False)
        if path.is_absolute()
        else resolve_workspace_path(path, must_exist=False)
    )
    if create:
        safe_path.mkdir(parents=True, exist_ok=True)
    return safe_path


def _display_path(path: Path) -> str:
    try:
        return relative_to_workspace(path)
    except Exception:
        return str(path)


def _ensure_inside_vault(path: Path, vault: Path) -> None:
    path.resolve(strict=False).relative_to(vault.resolve(strict=False))


def _default_memory() -> dict[str, Any]:
    return {
        "version": 1,
        "identity": "Hermes",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "entries": [],
        "facts": [],
        "preferences": [],
        "conflicts": [],
    }


def load_hermes_memory() -> dict[str, Any]:
    path = _memory_path()
    if not path.exists():
        return _default_memory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_memory()
    if not isinstance(data, dict):
        return _default_memory()
    data.setdefault("version", 1)
    data.setdefault("identity", "Hermes")
    data.setdefault("created_at", _now_iso())
    data["updated_at"] = data.get("updated_at") or _now_iso()
    for key in ("entries", "facts", "preferences", "conflicts"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def save_hermes_memory(memory: dict[str, Any]) -> None:
    memory["updated_at"] = _now_iso()
    _memory_path().write_text(json.dumps(memory, indent=2, ensure_ascii=False, default=str))


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-._")
    return normalized[:80] or "memory"


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_À-ÿ-]{3,}", value.lower())}


def _score_text(query: str, text: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokens(text)
    overlap = len(query_tokens & text_tokens)
    if overlap == 0:
        return 0.0
    return overlap / max(1, len(query_tokens))


def _safe_note_files() -> list[Path]:
    vault = obsidian_vault_path(create=True)
    files: list[Path] = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            if path.stat().st_size <= MAX_NOTE_BYTES:
                files.append(path)
        except OSError:
            continue
    return files


def search_obsidian_notes(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search Obsidian markdown notes using lightweight lexical ranking."""
    if not HERMES_MEMORY_ENABLED or not query.strip():
        return []
    results: list[dict[str, Any]] = []
    for path in _safe_note_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        score = _score_text(query, f"{path.name}\n{text}")
        if score <= 0:
            continue
        results.append(
            {
                "score": round(score, 6),
                "source": _display_path(path),
                "text": text[:MAX_RECALL_TEXT],
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            }
        )
    results.sort(key=lambda item: (item["score"], item["updated_at"]), reverse=True)
    return results[: max(1, int(top_k))]


def _entry_text(entry: dict[str, Any]) -> str:
    return "\n".join(
        str(entry.get(key, ""))
        for key in ("summary", "task", "result", "lessons", "tags")
        if entry.get(key)
    )


def search_json_memory(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search compact Hermes memory entries and facts."""
    if not HERMES_MEMORY_ENABLED or not query.strip():
        return []
    memory = load_hermes_memory()
    candidates: list[dict[str, Any]] = []
    for entry in memory.get("entries", []):
        if not isinstance(entry, dict):
            continue
        text = _entry_text(entry)
        score = _score_text(query, text)
        if score > 0:
            candidates.append(
                {
                    "score": round(score, 6),
                    "source": entry.get("id", "hermes_memory"),
                    "text": text[:MAX_RECALL_TEXT],
                    "updated_at": entry.get("updated_at") or entry.get("created_at"),
                }
            )
    candidates.sort(key=lambda item: (item["score"], str(item.get("updated_at") or "")), reverse=True)
    return candidates[: max(1, int(top_k))]


def _append_vector_document(kind: str, source: str, text: str, metadata: dict[str, Any]) -> None:
    store = vector_memory.load_vector_store()
    documents = [doc for doc in store.get("documents", []) if isinstance(doc, dict)]
    content_hash = vector_memory._content_hash(text)
    doc_id = f"{kind}:{source}:{content_hash[:12]}"
    embedding = vector_memory._hash_embedding(text)
    documents = [doc for doc in documents if doc.get("id") != doc_id]
    documents.append(
        {
            "id": doc_id,
            "kind": kind,
            "source": source,
            "chunk_index": 0,
            "content_hash": content_hash,
            "text": text,
            "embedding": embedding,
            "metadata": metadata,
            "updated_at": _now_iso(),
        }
    )
    store["documents"] = documents[-5000:]
    vector_memory.save_vector_store(store)
    _mirror_vector_document_to_qdrant(doc_id, kind, source, text, embedding, metadata)


def _mirror_vector_document_to_qdrant(
    doc_id: str,
    kind: str,
    source: str,
    text: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    if HERMES_MEMORY_BACKEND != "qdrant" or not embedding:
        return

    base_url = QDRANT_URL.rstrip("/")
    collection = QDRANT_COLLECTION.strip() or "hermes_memory"
    vector_size = len(embedding)
    try:
        requests.put(
            f"{base_url}/collections/{collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            timeout=3,
        )
        requests.put(
            f"{base_url}/collections/{collection}/points?wait=true",
            json={
                "points": [
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id)),
                        "vector": embedding,
                        "payload": {
                            "doc_id": doc_id,
                            "kind": kind,
                            "source": source,
                            "text": text[:MAX_RECALL_TEXT],
                            "metadata": metadata,
                            "updated_at": _now_iso(),
                        },
                    }
                ]
            },
            timeout=3,
        )
    except Exception:
        return


def _local_vector_search(query: str, kinds: set[str], top_k: int) -> list[dict[str, Any]]:
    store = vector_memory.load_vector_store()
    query_embedding = vector_memory._hash_embedding(query)
    results: list[dict[str, Any]] = []
    for doc in store.get("documents", []):
        if not isinstance(doc, dict) or doc.get("kind") not in kinds:
            continue
        embedding = doc.get("embedding")
        if not isinstance(embedding, list):
            continue
        score = vector_memory._cosine(query_embedding, [float(value) for value in embedding])
        results.append(
            {
                "score": round(score, 6),
                "kind": doc.get("kind"),
                "source": doc.get("source"),
                "text": doc.get("text", ""),
                "metadata": doc.get("metadata", {}),
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(1, int(top_k))]


def index_obsidian_vault(force: bool = False) -> dict[str, Any]:
    """Index Obsidian notes into the local vector store."""
    if not HERMES_MEMORY_ENABLED:
        return {"status": "disabled", "indexed": 0}
    store = vector_memory.load_vector_store()
    documents = [doc for doc in store.get("documents", []) if isinstance(doc, dict)]
    existing = {
        doc.get("source"): doc
        for doc in documents
        if doc.get("kind") == "obsidian_note" and doc.get("source")
    }
    documents = [doc for doc in documents if doc.get("kind") != "obsidian_note"]
    indexed = 0
    reused = 0
    for path in _safe_note_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        source = _display_path(path)
        content_hash = vector_memory._content_hash(text)
        previous = existing.get(source)
        if not force and previous and previous.get("content_hash") == content_hash:
            documents.append(previous)
            reused += 1
            continue
        documents.append(
            {
                "id": f"obsidian:{source}:{content_hash[:12]}",
                "kind": "obsidian_note",
                "source": source,
                "chunk_index": 0,
                "content_hash": content_hash,
                "text": text[:MAX_RECALL_TEXT],
                "embedding": vector_memory._hash_embedding(f"{source}\n{text}"),
                "metadata": {"path": source},
                "updated_at": _now_iso(),
            }
        )
        indexed += 1
    store["documents"] = documents
    vector_memory.save_vector_store(store)
    return {
        "status": "indexed",
        "vault": _display_path(obsidian_vault_path(create=True)),
        "indexed": indexed,
        "reused": reused,
        "total_documents": len(documents),
    }


def write_obsidian_note(title: str, content: str, folder: str = "Hermes") -> dict[str, Any]:
    """Write a sandboxed markdown note into the configured Obsidian vault."""
    vault = obsidian_vault_path(create=True)
    safe_folder = _slug(folder)
    target_dir = (vault / safe_folder).resolve(strict=False)
    _ensure_inside_vault(target_dir, vault)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slug(title)}.md"
    target = (target_dir / filename).resolve(strict=False)
    _ensure_inside_vault(target, vault)
    target.write_text(content, encoding="utf-8")
    return {"success": True, "path": _display_path(target)}


def _daily_memory_path(day: str | None = None) -> Path:
    vault = obsidian_vault_path(create=True)
    date_text = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_dir = _slug(OBSIDIAN_DAILY_MEMORY_DIR or "memories")
    target_dir = (vault / safe_dir).resolve(strict=False)
    _ensure_inside_vault(target_dir, vault)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / f"{date_text}.md").resolve(strict=False)
    _ensure_inside_vault(target, vault)
    return target


def _daily_memory_section(entry: dict[str, Any]) -> str:
    tags = {str(tag).lower() for tag in entry.get("tags", [])}
    category = str(entry.get("category", "")).lower()
    text = " ".join(
        str(entry.get(key, "")).lower() for key in ("summary", "task", "result")
    )
    if "user-preference" in tags or "preference" in tags or category == "user":
        return "User preferences"
    if "project" in tags or category == "project" or "project" in text:
        return "Projects"
    if "insight" in tags or category == "insight":
        return "Insights"
    return "Key facts"


def _daily_memory_template(date_text: str) -> str:
    return (
        f"# Memory - {date_text}\n\n"
        "## Key facts\n\n"
        "## User preferences\n\n"
        "## Projects\n\n"
        "## Insights\n"
    )


def _ensure_daily_memory_template(content: str, date_text: str) -> str:
    if not content.strip():
        return _daily_memory_template(date_text)

    lines = content.splitlines()
    if lines and lines[0].startswith("# Memories - "):
        lines[0] = f"# Memory - {date_text}"
        content = "\n".join(lines)

    content = content.replace(
        "\nConcise long-term memory extracted from interactions.\n", "\n"
    )
    content = content.replace("\n## Entries\n", "\n## Key facts\n")

    if not content.startswith(f"# Memory - {date_text}"):
        content = f"# Memory - {date_text}\n\n" + content.lstrip()

    for section in ("Key facts", "User preferences", "Projects", "Insights"):
        heading = f"## {section}"
        if heading not in content:
            content = content.rstrip() + f"\n\n{heading}\n"
    return content


def _append_to_daily_section(content: str, section: str, block: str) -> str:
    heading = f"## {section}"
    marker = content.find(heading)
    if marker == -1:
        return content.rstrip() + f"\n\n{heading}\n\n{block.lstrip()}"

    next_marker = content.find("\n## ", marker + len(heading))
    insert_at = len(content) if next_marker == -1 else next_marker
    before = content[:insert_at].rstrip()
    after = content[insert_at:].lstrip("\n")
    updated = before + "\n\n" + block.strip() + "\n"
    if after:
        updated += "\n" + after
    return updated


def append_daily_memory_summary(entry: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    """Append a concise durable-memory summary to the daily Obsidian memory note."""
    if not HERMES_MEMORY_ENABLED:
        return {"success": True, "status": "disabled"}

    path = _daily_memory_path(day)
    entry_id = str(entry.get("id") or "")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if entry_id and f"<!-- {entry_id} -->" in existing:
        return {"success": True, "status": "duplicate", "path": _display_path(path)}

    date_text = path.stem
    existing = _ensure_daily_memory_template(existing, date_text)

    tags = ", ".join(str(tag) for tag in entry.get("tags", [])[:10])
    lessons = entry.get("lessons") if isinstance(entry.get("lessons"), list) else []
    lesson_text = "; ".join(str(lesson) for lesson in lessons[:3])
    block = (
        f"\n<!-- {entry_id} -->\n"
        f"- **{entry.get('summary', 'Memory')}**\n"
        f"  - Task: {entry.get('task', '')}\n"
        f"  - Tags: {tags}\n"
        f"  - Lessons: {lesson_text}\n"
    )
    section = _daily_memory_section(entry)
    path.write_text(_append_to_daily_section(existing, section, block), encoding="utf-8")
    _append_vector_document(
        "obsidian_daily_memory",
        _display_path(path),
        block,
        {"entry_id": entry_id, "tags": entry.get("tags", [])},
    )
    return {"success": True, "status": "written", "path": _display_path(path)}


def store_hermes_memory(
    summary: str,
    task: str = "",
    result: str = "",
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
    write_note: bool = True,
) -> dict[str, Any]:
    """Store a compact long-term memory entry and mirror it to vector memory."""
    if not HERMES_MEMORY_ENABLED:
        return {"success": True, "status": "disabled"}
    memory = load_hermes_memory()
    entry = {
        "id": f"hermes-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "summary": summary.strip()[:1200],
        "task": task.strip()[:1000],
        "result": result.strip()[:1200],
        "lessons": [str(item)[:300] for item in (lessons or [])[:8]],
        "tags": [str(item)[:80] for item in (tags or [])[:12]],
    }
    memory["entries"].append(entry)
    memory["entries"] = memory["entries"][-1000:]
    save_hermes_memory(memory)
    text = _entry_text(entry)
    _append_vector_document("hermes_memory", str(entry["id"]), text, {"tags": entry["tags"]})
    note = None
    if write_note:
        note_body = (
            f"# {entry['summary'] or 'Hermes Memory'}\n\n"
            f"- Created: {entry['created_at']}\n"
            f"- Tags: {', '.join(entry['tags'])}\n\n"
            f"## Task\n{entry['task']}\n\n"
            f"## Result\n{entry['result']}\n\n"
            f"## Lessons\n"
            + "\n".join(f"- {lesson}" for lesson in entry["lessons"])
            + "\n"
        )
        note = write_obsidian_note(entry["summary"] or "Hermes memory", note_body, folder="Hermes")
    daily_note = append_daily_memory_summary(entry)
    return {"success": True, "entry": entry, "note": note, "daily_note": daily_note}


def remember_interaction(task: str, result: Any, memory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize a completed or blocked run into durable Hermes memory."""
    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    lessons: list[str] = []
    if isinstance(memory, dict):
        if memory.get("last_success_evaluation"):
            lessons.append(f"Validation: {str(memory.get('last_success_evaluation'))[:280]}")
        if memory.get("last_debugger_report"):
            lessons.append(f"Debugger: {str(memory.get('last_debugger_report'))[:280]}")
        if memory.get("last_review_report"):
            lessons.append(f"Review: {str(memory.get('last_review_report'))[:280]}")
    summary = task.strip().splitlines()[0][:180] or "Interaction completed"
    return store_hermes_memory(
        summary=summary,
        task=task,
        result=result_text,
        lessons=lessons,
        tags=["interaction", "autonomous-run"],
        write_note=True,
    )


def _memory_match_priority(match: dict[str, Any]) -> str:
    metadata = match.get("metadata") if isinstance(match.get("metadata"), dict) else {}
    tags = {
        str(tag).lower()
        for tag in (
            list(match.get("tags", []) or [])
            + list(metadata.get("tags", []) or [])
        )
    }
    text = str(match.get("text", "")).lower()
    if "high" in tags or "high" in text:
        return "high"
    return "normal"


def _is_high_confidence_memory_match(match: dict[str, Any]) -> bool:
    score = float(match.get("score") or 0.0)
    priority = _memory_match_priority(match)
    if priority == "high" and score >= 0.25:
        return True
    return score >= 0.35


def _memory_fact(match: dict[str, Any]) -> str:
    text = str(match.get("text", "")).strip()
    skipped_headings = {"key facts", "user preferences", "projects", "insights"}
    for line in text.splitlines():
        raw_line = line.lstrip()
        if raw_line.startswith("#"):
            continue
        fact = line.strip(" -#*")
        normalized = fact.lower()
        if (
            not fact
            or normalized.startswith("memory - ")
            or normalized.startswith("<!--")
            or normalized.startswith("created:")
            or normalized.startswith("tags:")
            or normalized in skipped_headings
        ):
            continue
        if fact:
            return fact[:240]
    return "Relevant memory found."


def _memory_context_block(matches: list[dict[str, Any]], limit: int) -> str:
    facts = []
    seen = set()
    for match in matches:
        if not _is_high_confidence_memory_match(match):
            continue
        fact = _memory_fact(match)
        key = fact.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)
        if len(facts) >= limit:
            break

    if not facts:
        return "### Memory Context"
    return "### Memory Context\n" + "\n".join(f"- {fact}" for fact in facts)


def hermes_recall(query: str, top_k: int = 5) -> dict[str, Any]:
    """Retrieve relevant long-term memory, Obsidian notes, and vector matches."""
    if not HERMES_MEMORY_ENABLED:
        return {"enabled": False, "context": "### Memory Context"}
    index_result = index_obsidian_vault(force=False)
    json_matches = search_json_memory(query, top_k=top_k)
    note_matches = search_obsidian_notes(query, top_k=top_k)
    vector_matches = _local_vector_search(
        query,
        kinds={"hermes_memory", "obsidian_note", "obsidian_daily_memory", "agent_history"},
        top_k=top_k,
    )

    ranked_matches = sorted(
        [*json_matches, *note_matches, *vector_matches],
        key=lambda match: float(match.get("score") or 0.0),
        reverse=True,
    )
    return {
        "enabled": True,
        "index": index_result,
        "json_matches": json_matches,
        "obsidian_matches": note_matches,
        "vector_matches": vector_matches,
        "context": _memory_context_block(ranked_matches, top_k),
    }


def hermes_context_text(query: str) -> str:
    try:
        return str(hermes_recall(query=query, top_k=4).get("context", "No Hermes memory found."))
    except Exception as exc:
        return f"Hermes memory unavailable: {exc}"


__all__ = [
    "hermes_context_text",
    "hermes_recall",
    "index_obsidian_vault",
    "load_hermes_memory",
    "obsidian_vault_path",
    "append_daily_memory_summary",
    "remember_interaction",
    "save_hermes_memory",
    "search_json_memory",
    "search_obsidian_notes",
    "store_hermes_memory",
    "write_obsidian_note",
]
