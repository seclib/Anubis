from __future__ import annotations

from pathlib import Path
from typing import Any

from anubis.context.compressor.compressor import ContextCompressor
from anubis.context.embeddings import EmbeddingProvider, tokenize
from anubis.context.indexer.indexer import RepositoryIndexer
from anubis.context.retriever.retriever import HybridContextRetriever
from anubis.context.schema import (
    BuiltContext,
    ContextBudget,
    ContextBuildRequest,
    MinimalContext,
    RankedFile,
    RepositoryIndex,
    RetrievedContext,
)


class ContextBuilder:
    def __init__(
        self,
        root: Path | str,
        embedding_provider: EmbeddingProvider | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.indexer = RepositoryIndexer(self.root, embedding_provider)
        self.retriever = HybridContextRetriever(embedding_provider)
        self.compressor = compressor or ContextCompressor()

    def build(self, task: str, top_k: int = 8, index: RepositoryIndex | None = None) -> BuiltContext:
        repository_index = index or self.indexer.index_repository()
        retrieved = self.retriever.retrieve(repository_index, task, top_k=top_k)
        context_chunks, summary = self.compressor.compress(task, retrieved)
        return BuiltContext(task=task, context_chunks=context_chunks, summary=summary)

    def build_minimal(
        self,
        request: ContextBuildRequest | str,
        *,
        repo_state: dict[str, Any] | None = None,
        memory: dict[str, Any] | None = None,
        budget: ContextBudget | None = None,
        index: RepositoryIndex | None = None,
    ) -> MinimalContext:
        build_request = _normalize_request(request, repo_state=repo_state, memory=memory, budget=budget)
        normalized_budget = _normalize_budget(build_request.budget)
        repository_index = index or self.indexer.index_repository()
        top_k = max(normalized_budget.max_files * normalized_budget.max_chunks_per_file * 3, normalized_budget.max_files)
        retrieved = self.retriever.retrieve(repository_index, build_request.task, top_k=top_k)
        ranked_files = self._rank_files(retrieved, build_request, normalized_budget)
        selected, omitted = self._select_files(ranked_files, normalized_budget)
        selected_memory = self._select_memory(build_request, normalized_budget)
        context, estimated_tokens = _render_context(build_request.task, selected, selected_memory, normalized_budget)
        return MinimalContext(
            task=build_request.task,
            files=tuple(selected),
            memory=tuple(selected_memory),
            context=context,
            estimated_tokens=estimated_tokens,
            token_budget=normalized_budget.max_tokens,
            omitted_files=tuple(omitted),
        )

    def _rank_files(
        self,
        retrieved: tuple[RetrievedContext, ...],
        request: ContextBuildRequest,
        budget: ContextBudget,
    ) -> list[RankedFile]:
        grouped: dict[str, list[RetrievedContext]] = {}
        for item in retrieved:
            grouped.setdefault(item.chunk.file_path, []).append(item)

        ranked: list[RankedFile] = []
        repo_state = request.repo_state
        changed_files = _path_set(repo_state.get("changed_files"))
        open_files = _path_set(repo_state.get("open_files"))
        recent_files = _path_set(repo_state.get("recent_files"))
        task_terms = set(tokenize(request.task))

        for path, items in grouped.items():
            best = max(item.score for item in items)
            boost = 0.0
            reasons = [f"retrieval={best:.3f}"]
            if path in changed_files:
                boost += 0.20
                reasons.append("changed")
            if path in open_files:
                boost += 0.12
                reasons.append("open")
            if path in recent_files:
                boost += 0.08
                reasons.append("recent")
            if any(term in path.lower() for term in task_terms):
                boost += 0.10
                reasons.append("path_match")

            chunks = []
            for item in items[: budget.max_chunks_per_file]:
                content = _trim_content(item.chunk.content, request.task, max_chars=900)
                chunks.append(
                    {
                        "file": item.chunk.file_path,
                        "content": content,
                        "score": item.score,
                        "start_line": item.chunk.start_line,
                        "end_line": item.chunk.end_line,
                        "symbols": list(item.chunk.symbols),
                    }
                )
            estimated = sum(_estimate_tokens(str(chunk["content"])) for chunk in chunks)
            ranked.append(
                RankedFile(
                    path=path,
                    score=round(min(1.0, best + boost), 6),
                    reason=", ".join(reasons),
                    chunks=tuple(chunks),
                    estimated_tokens=estimated,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.path))
        return ranked

    def _select_files(self, ranked_files: list[RankedFile], budget: ContextBudget) -> tuple[list[RankedFile], list[str]]:
        selected: list[RankedFile] = []
        used = 0
        file_budget_tokens = max(1, budget.max_tokens - budget.reserved_memory_tokens)
        max_files = max(1, budget.max_files)
        for item in ranked_files:
            if len(selected) >= max_files:
                break
            if selected and used + item.estimated_tokens > file_budget_tokens and len(selected) >= budget.min_files:
                break
            selected.append(item)
            used += item.estimated_tokens
        omitted = [item.path for item in ranked_files if item.path not in {selected_file.path for selected_file in selected}]
        return selected, omitted

    def _select_memory(self, request: ContextBuildRequest, budget: ContextBudget) -> list[dict[str, Any]]:
        memory_items = _memory_items(request.memory)
        if not memory_items or budget.reserved_memory_tokens <= 0:
            return []
        task_terms = set(tokenize(request.task))
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index, item in enumerate(memory_items):
            text = str(item.get("text") or item.get("content") or item.get("summary") or item.get("value") or "")
            terms = set(tokenize(text))
            score = len(task_terms & terms) / max(1, len(task_terms))
            if score <= 0:
                continue
            ranked.append((score, index, {"text": text[:800], "score": round(score, 6), "source": item.get("source", "memory")}))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected: list[dict[str, Any]] = []
        used = 0
        for _score, _index, item in ranked:
            tokens = _estimate_tokens(str(item["text"]))
            if selected and used + tokens > budget.reserved_memory_tokens:
                break
            selected.append(item)
            used += tokens
        return selected


def _normalize_request(
    request: ContextBuildRequest | str,
    *,
    repo_state: dict[str, Any] | None,
    memory: dict[str, Any] | None,
    budget: ContextBudget | None,
) -> ContextBuildRequest:
    if isinstance(request, ContextBuildRequest):
        return request
    return ContextBuildRequest(
        task=str(request),
        repo_state=dict(repo_state or {}),
        memory=dict(memory or {}),
        budget=budget or ContextBudget(),
    )


def _normalize_budget(budget: ContextBudget) -> ContextBudget:
    max_files = min(5, max(1, int(budget.max_files)))
    min_files = min(max_files, max(1, int(budget.min_files)))
    return ContextBudget(
        max_tokens=max(256, int(budget.max_tokens)),
        max_files=max_files,
        min_files=min_files,
        max_chunks_per_file=max(1, int(budget.max_chunks_per_file)),
        reserved_memory_tokens=max(0, int(budget.reserved_memory_tokens)),
    )


def _path_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _memory_items(memory: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("items", "entries", "memories", "facts", "recent"):
        value = memory.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    items.append(item)
                else:
                    items.append({"text": str(item), "source": key})
    for key, value in memory.items():
        if key in {"items", "entries", "memories", "facts", "recent"}:
            continue
        if isinstance(value, str):
            items.append({"text": value, "source": key})
    return items


def _trim_content(content: str, task: str, *, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    terms = set(tokenize(task))
    lines = content.splitlines()
    scored = []
    for index, line in enumerate(lines):
        score = len(terms & set(tokenize(line)))
        scored.append((score, index, line))
    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:30]
    selected_indexes = sorted(index for _score, index, _line in selected)
    return "\n".join(lines[index] for index in selected_indexes)[:max_chars]


def _render_context(
    task: str,
    files: list[RankedFile],
    memory: list[dict[str, Any]],
    budget: ContextBudget,
) -> tuple[str, int]:
    blocks = [f"Task: {task.strip()}"]
    if memory:
        blocks.append("Memory:\n" + "\n".join(f"- {item['text']} (score={item['score']})" for item in memory))
    for file in files:
        chunk_text = "\n\n".join(
            f"{chunk['file']}:{chunk['start_line']}-{chunk['end_line']} score={chunk['score']}\n{chunk['content']}"
            for chunk in file.chunks
        )
        blocks.append(f"File: {file.path}\nReason: {file.reason}\n{chunk_text}")
    context = "\n\n---\n\n".join(blocks)
    if _estimate_tokens(context) <= budget.max_tokens:
        return context, _estimate_tokens(context)
    return _truncate_to_tokens(context, budget.max_tokens), budget.max_tokens


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    return text[: max(1, max_tokens * 4)]


__all__ = ["ContextBuilder"]
