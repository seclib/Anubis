import logging
from typing import Protocol

import requests

from backend.core.config import settings


logger = logging.getLogger("anubis.agent.llm")


class LLM(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class OllamaLLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 120) -> None:
        self.model = model or settings.llm_model
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            return str(data)
        except Exception as exc:  # pragma: no cover - depends on local Ollama availability
            logger.warning("ollama unavailable; using deterministic fallback: %s", exc)
            return ""


class FallbackLLM:
    def generate(self, prompt: str) -> str:
        return ""
