"""Hermes long-term memory backed by JSON, Obsidian notes, and vector recall."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent import vector_memory
from config import HERMES_MEMORY_ENABLED, HERMES_MEMORY_FILE, OBSIDIAN_VAULT_PATH
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
    safe_path = resolve_workspace_path(path, must_exist=False)
    if create:
        safe_path.mkdir(parents=True, exist_ok=True)
    return safe_path


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
                "source": relative_to_workspace(path),
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
    documents = [doc for doc in documents if doc.get("id") != doc_id]
    documents.append(
        {
            "id": doc_id,
            "kind": kind,
            "source": source,
            "chunk_index": 0,
            "content_hash": content_hash,
            "text": text,
            "embedding": vector_memory._hash_embedding(text),
            "metadata": metadata,
            "updated_at": _now_iso(),
        }
    )
    store["documents"] = documents[-5000:]
    vector_memory.save_vector_store(store)


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
        source = relative_to_workspace(path)
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
        "vault": relative_to_workspace(obsidian_vault_path(create=True)),
        "indexed": indexed,
        "reused": reused,
        "total_documents": len(documents),
    }


def write_obsidian_note(title: str, content: str, folder: str = "Hermes") -> dict[str, Any]:
    """Write a sandboxed markdown note into the configured Obsidian vault."""
    vault = obsidian_vault_path(create=True)
    safe_folder = _slug(folder)
    target_dir = resolve_workspace_path(vault / safe_folder, must_exist=False)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slug(title)}.md"
    target = resolve_workspace_path(target_dir / filename, must_exist=False)
    target.write_text(content, encoding="utf-8")
    return {"success": True, "path": relative_to_workspace(target)}


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
    return {"success": True, "entry": entry, "note": note}


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


def hermes_recall(query: str, top_k: int = 5) -> dict[str, Any]:
    """Retrieve relevant long-term memory, Obsidian notes, and vector matches."""
    if not HERMES_MEMORY_ENABLED:
        return {"enabled": False, "context": "Hermes memory disabled."}
    index_result = index_obsidian_vault(force=False)
    json_matches = search_json_memory(query, top_k=top_k)
    note_matches = search_obsidian_notes(query, top_k=top_k)
    vector_matches = _local_vector_search(
        query,
        kinds={"hermes_memory", "obsidian_note", "agent_history"},
        top_k=top_k,
    )

    blocks = []
    for label, matches in (
        ("Hermes JSON memory", json_matches),
        ("Obsidian notes", note_matches),
        ("Vector recall", vector_matches),
    ):
        if not matches:
            continue
        blocks.append(label + ":")
        for match in matches[:top_k]:
            blocks.append(
                f"- [{match.get('source')} score={match.get('score')}] "
                f"{str(match.get('text', ''))[:500]}"
            )
    return {
        "enabled": True,
        "index": index_result,
        "json_matches": json_matches,
        "obsidian_matches": note_matches,
        "vector_matches": vector_matches,
        "context": "\n".join(blocks) if blocks else "No relevant Hermes memory found.",
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
    "remember_interaction",
    "save_hermes_memory",
    "search_json_memory",
    "search_obsidian_notes",
    "store_hermes_memory",
    "write_obsidian_note",
]
