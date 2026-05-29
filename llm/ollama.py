"""Ollama LLM client — blocking, streaming, and chat interfaces."""

import json
import logging
import time
from typing import Any, Generator, Optional

import requests

from config import (
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    OLLAMA_BASE_URL,
    OLLAMA_FALLBACK_MODEL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
)

logger = logging.getLogger(__name__)

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
DEFAULT_MODEL = OLLAMA_MODEL
FALLBACK_MODEL = OLLAMA_FALLBACK_MODEL
MAX_RETRIES = 3
TIMEOUT = 180  # LLM local sur CPU peut prendre jusqu'à 90s
RETRY_DELAY = 2.0  # secondes entre chaque tentative


def _ollama_options(
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    return {
        "temperature": temperature if temperature is not None else LLM_TEMPERATURE,
        "num_predict": max_tokens if max_tokens is not None else LLM_MAX_TOKENS,
        "num_ctx": OLLAMA_NUM_CTX,
    }


def _fallback_enabled(current_model: str) -> bool:
    return bool(FALLBACK_MODEL) and current_model != FALLBACK_MODEL


def _parse_response(data: dict) -> Optional[str]:
    """Extraire le texte généré depuis la réponse Ollama."""
    for key in ("response", "text", "output", "result", "generated_text"):
        if key in data:
            val = data[key]
            return val if isinstance(val, str) else str(val)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            for k in ("text", "message", "content"):
                if k in first:
                    v = first[k]
                    return v if isinstance(v, str) else str(v)
            return str(first)
    # Chat endpoint returns message.content
    message = data.get("message")
    if isinstance(message, dict) and "content" in message:
        return str(message["content"])
    return str(data)


def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Blocking single-prompt call via Ollama /api/chat."""
    return call_chat([{"role": "user", "content": prompt}], model=model)


def call_generate(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Blocking single-prompt call via /api/generate for legacy diagnostics."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": _ollama_options(),
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }
    last_err: Optional[Exception] = None
    current_model = model

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            return _parse_response(resp.json())
        except Exception as e:
            last_err = e
            logger.warning(
                "LLM attempt %d/%d failed (model=%s): %s",
                attempt + 1, MAX_RETRIES, current_model, e,
            )
            # Basculer sur le modèle de fallback à la 2e tentative
            if attempt == 1 and _fallback_enabled(current_model):
                current_model = FALLBACK_MODEL
                payload["model"] = FALLBACK_MODEL
                logger.info("Switching to fallback model: %s", FALLBACK_MODEL)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return f"[LLM ERROR] {last_err}"


def call_chat(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Blocking multi-message call via /api/chat (non-streaming)."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(temperature=temperature, max_tokens=max_tokens),
    }
    last_err: Optional[Exception] = None
    current_model = model

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content") or _parse_response(data)
        except Exception as e:
            last_err = e
            logger.warning(
                "Chat attempt %d/%d failed (model=%s): %s",
                attempt + 1, MAX_RETRIES, current_model, e,
            )
            if attempt == 1 and _fallback_enabled(current_model):
                current_model = FALLBACK_MODEL
                payload["model"] = FALLBACK_MODEL
                logger.info("Switching to fallback model: %s", FALLBACK_MODEL)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return f"[LLM ERROR] {last_err}"


def stream_chat(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Generator[str, None, None]:
    """Streaming multi-message call via /api/chat — yields tokens one by one."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(temperature=temperature, max_tokens=max_tokens),
    }
    current_model = model

    for attempt in range(MAX_RETRIES):
        try:
            with requests.post(
                OLLAMA_CHAT_URL,
                json=payload,
                timeout=TIMEOUT,
                stream=True,
            ) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    try:
                        chunk = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        return
                return  # stream ended cleanly
        except Exception as e:
            logger.warning(
                "Stream attempt %d/%d failed (model=%s): %s",
                attempt + 1, MAX_RETRIES, current_model, e,
            )
            if attempt == 1 and _fallback_enabled(current_model):
                current_model = FALLBACK_MODEL
                payload["model"] = FALLBACK_MODEL
                logger.info("Switching to fallback model: %s", FALLBACK_MODEL)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    yield f"[LLM ERROR] streaming failed after {MAX_RETRIES} attempts"


__all__ = ["call_generate", "call_llm", "call_chat", "stream_chat"]
