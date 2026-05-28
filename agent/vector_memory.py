"""Local vector memory for repository RAG and agent history."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import (
    EMBEDDING_FALLBACK_ENABLED,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT,
    OLLAMA_BASE_URL,
    VECTOR_STORE_FILE,
)
from tools.sandbox import relative_to_workspace, resolve_workspace_path, workspace_root

MAX_CHARS_PER_CHUNK = 2200
CHUNK_OVERLAP = 250
MAX_FILE_BYTES = 256_000

IGNORED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".sqlite",
    ".db",
}

IGNORED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    path = Path(VECTOR_STORE_FILE)
    if not path.is_absolute():
        path = workspace_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "embedding_model": EMBEDDING_MODEL,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "documents": [],
    }


def load_vector_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()

    try:
        data = json.loads(path.read_text())
    except Exception:
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()
    if not isinstance(data.get("documents"), list):
        data["documents"] = []
    data.setdefault("version", 1)
    data.setdefault("embedding_model", EMBEDDING_MODEL)
    data.setdefault("created_at", _now_iso())
    data["updated_at"] = data.get("updated_at") or _now_iso()
    return data


def save_vector_store(store: dict[str, Any]) -> None:
    store["updated_at"] = _now_iso()
    _store_path().write_text(json.dumps(store, indent=2, ensure_ascii=False, default=str))


def _ollama_embedding(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    base_url = OLLAMA_BASE_URL.rstrip("/")
    errors: list[str] = []

    for endpoint, payload in (
        ("/api/embed", {"model": model, "input": text}),
        ("/api/embeddings", {"model": model, "prompt": text}),
    ):
        try:
            response = requests.post(
                f"{base_url}{endpoint}",
                json=payload,
                timeout=EMBEDDING_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            embeddings = data.get("embeddings")
            if isinstance(embedding, list):
                return [float(value) for value in embedding]
            if isinstance(embeddings, list) and embeddings:
                first = embeddings[0]
                if isinstance(first, list):
                    return [float(value) for value in first]
        except Exception as exc:
            errors.append(str(exc))

    if EMBEDDING_FALLBACK_ENABLED:
        return _hash_embedding(text)

    raise RuntimeError(f"Ollama embedding failed for model {model}: {' | '.join(errors)}")


def _hash_embedding(text: str, dimensions: int = 256) -> list[float]:
    vector = [0.0] * dimensions
    tokens = [token for token in text.lower().replace("_", " ").replace("-", " ").split() if token]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    return _normalize(vector)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def embed_text(text: str) -> list[float]:
    return _normalize(_ollama_embedding(text))


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _is_indexable_file(path: Path) -> bool:
    try:
        if path.resolve(strict=False) == _store_path().resolve(strict=False):
            return False
    except OSError:
        return False
    if any(part in IGNORED_PARTS for part in path.parts):
        return False
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return False
    if not path.is_file():
        return False
    try:
        return path.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return None


def _chunks(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _repo_files(root: str = ".") -> list[Path]:
    root_path = resolve_workspace_path(root, must_exist=True)
    if root_path.is_file():
        return [root_path] if _is_indexable_file(root_path) else []
    return [
        path
        for path in sorted(root_path.rglob("*"))
        if _is_indexable_file(path)
    ]


def index_repository(root: str = ".", force: bool = False) -> dict[str, Any]:
    store = load_vector_store()
    documents = store.get("documents", [])
    if not isinstance(documents, list):
        documents = []

    existing_by_source = {
        doc.get("source"): doc
        for doc in documents
        if isinstance(doc, dict) and doc.get("source") and doc.get("kind") == "repository"
    }
    non_repo_docs = [
        doc
        for doc in documents
        if isinstance(doc, dict) and doc.get("kind") != "repository"
    ]

    indexed_docs: list[dict[str, Any]] = []
    indexed_files = 0
    indexed_chunks = 0
    skipped_files = 0

    for path in _repo_files(root):
        text = _read_text(path)
        if text is None:
            skipped_files += 1
            continue
        source = relative_to_workspace(path)
        content_hash = _content_hash(text)
        source_docs = [
            doc for doc in documents
            if isinstance(doc, dict)
            and doc.get("kind") == "repository"
            and doc.get("source") == source
        ]
        if (
            not force
            and source_docs
            and all(doc.get("content_hash") == content_hash for doc in source_docs)
        ):
            indexed_docs.extend(source_docs)
            continue

        chunks = _chunks(text)
        if not chunks:
            skipped_files += 1
            continue

        indexed_files += 1
        for chunk_index, chunk in enumerate(chunks):
            indexed_chunks += 1
            indexed_docs.append(
                {
                    "id": f"repo:{source}:{chunk_index}:{content_hash[:12]}",
                    "kind": "repository",
                    "source": source,
                    "chunk_index": chunk_index,
                    "content_hash": content_hash,
                    "text": chunk,
                    "embedding": embed_text(f"{source}\n{chunk}"),
                    "metadata": {
                        "path": source,
                        "size": len(text),
                    },
                    "updated_at": _now_iso(),
                }
            )

    store["documents"] = non_repo_docs + indexed_docs
    store["embedding_model"] = EMBEDDING_MODEL
    save_vector_store(store)

    return {
        "status": "indexed",
        "root": relative_to_workspace(resolve_workspace_path(root, must_exist=True)),
        "files_changed": indexed_files,
        "chunks_changed": indexed_chunks,
        "repository_documents": len(indexed_docs),
        "total_documents": len(store["documents"]),
        "skipped_files": skipped_files,
        "store": relative_to_workspace(_store_path()),
        "embedding_model": EMBEDDING_MODEL,
        "reused_sources": len(existing_by_source) - indexed_files if existing_by_source else 0,
    }


def index_agent_history(memory: dict[str, Any]) -> dict[str, Any]:
    store = load_vector_store()
    documents = [
        doc
        for doc in store.get("documents", [])
        if isinstance(doc, dict) and doc.get("kind") != "agent_history"
    ]

    messages = memory.get("agent_messages", [])
    if not isinstance(messages, list):
        messages = []

    indexed = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        text = json.dumps(message, ensure_ascii=False, default=str)
        content_hash = _content_hash(text)
        documents.append(
            {
                "id": f"agent_history:{index}:{content_hash[:12]}",
                "kind": "agent_history",
                "source": str(message.get("agent", "unknown_agent")),
                "chunk_index": index,
                "content_hash": content_hash,
                "text": text,
                "embedding": embed_text(text),
                "metadata": {
                    "agent": message.get("agent"),
                    "phase": message.get("phase"),
                },
                "updated_at": _now_iso(),
            }
        )
        indexed += 1

    store["documents"] = documents
    save_vector_store(store)
    return {
        "status": "indexed",
        "agent_history_documents": indexed,
        "total_documents": len(documents),
        "store": relative_to_workspace(_store_path()),
    }


def semantic_search(query: str, top_k: int = 5, kind: str | None = None) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    store = load_vector_store()
    documents = [doc for doc in store.get("documents", []) if isinstance(doc, dict)]
    if kind:
        documents = [doc for doc in documents if doc.get("kind") == kind]
    if not documents:
        return []

    query_embedding = embed_text(query)
    results: list[dict[str, Any]] = []

    for doc in documents:
        embedding = doc.get("embedding")
        if not isinstance(embedding, list):
            continue
        score = _cosine(query_embedding, [float(value) for value in embedding])
        results.append(
            {
                "score": round(score, 6),
                "kind": doc.get("kind"),
                "source": doc.get("source"),
                "chunk_index": doc.get("chunk_index"),
                "text": doc.get("text", ""),
                "metadata": doc.get("metadata", {}),
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(1, int(top_k))]


def retrieve_context(query: str, top_k: int = 5) -> str:
    results = semantic_search(query=query, top_k=top_k)
    if not results:
        return "No relevant vector context found."

    blocks = []
    for result in results:
        source = result.get("source")
        score = result.get("score")
        text = str(result.get("text", ""))[:1200]
        blocks.append(f"[{source} score={score}]\n{text}")
    return "\n\n".join(blocks)


__all__ = [
    "embed_text",
    "index_agent_history",
    "index_repository",
    "load_vector_store",
    "retrieve_context",
    "save_vector_store",
    "semantic_search",
]
