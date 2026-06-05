from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterator
from urllib import request


@dataclass(frozen=True)
class RoutedModel:
    model: str
    reason: str


class OllamaRouter:
    """Cheap intent router for local Ollama models."""

    def __init__(
        self,
        *,
        default_model: str | None = None,
        code_model: str | None = None,
        fast_model: str | None = None,
        review_model: str | None = None,
    ) -> None:
        fallback = default_model or os.environ.get("ANUBIS_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "qwen2.5-coder:7b"
        self.default_model = fallback
        self.code_model = code_model or os.environ.get("ANUBIS_OLLAMA_CODE_MODEL") or fallback
        self.fast_model = fast_model or os.environ.get("ANUBIS_OLLAMA_FAST_MODEL") or fallback
        self.review_model = review_model or os.environ.get("ANUBIS_OLLAMA_REVIEW_MODEL") or self.code_model

    def route(self, prompt: str, *, role: str = "assistant") -> RoutedModel:
        text = prompt.lower()
        if role in {"planner", "executor"} or any(word in text for word in ("code", "file", "test", "bug", "shell", "repo")):
            return RoutedModel(self.code_model, "coding or repository task")
        if role in {"reviewer", "critic"}:
            return RoutedModel(self.review_model, "review and verification task")
        if len(prompt) < 400:
            return RoutedModel(self.fast_model, "short conversational turn")
        return RoutedModel(self.default_model, "default local model")


class OllamaClient:
    def __init__(self, host: str | None = None, timeout: int = 120) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
        self.timeout = timeout

    def stream_chat(self, model: str, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = json.dumps({"model": model, "messages": messages, "stream": True}).encode("utf-8")
        req = request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line.decode("utf-8"))
                message = item.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        yield content
                if item.get("done"):
                    break

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        return "".join(self.stream_chat(model, messages))


__all__ = ["OllamaClient", "OllamaRouter", "RoutedModel"]
