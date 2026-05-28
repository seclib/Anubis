"""FastAPI entrypoint exposing OpenAI-compatible chat completions."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

PROJECT_SOURCE = Path(__file__).resolve().parent.parent
if str(PROJECT_SOURCE) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE))

from agent.loop import run_agent_loop
from config import (
    API_AUTH_REQUIRED,
    API_BASE_PATH,
    API_HOST,
    API_KEY,
    API_MODEL_ID,
    API_MODEL_NAME,
    API_PORT,
    LOG_LEVEL,
)

logger = logging.getLogger(__name__)

_STREAM_DONE = object()
_API_PREFIX = API_BASE_PATH
_MODELS_PATH = f"{_API_PREFIX}/models" if _API_PREFIX else "/models"
_MODEL_DETAIL_PATH = f"{_API_PREFIX}/models/{{model_id}}" if _API_PREFIX else "/models/{model_id}"
_CHAT_COMPLETIONS_PATH = (
    f"{_API_PREFIX}/chat/completions" if _API_PREFIX else "/chat/completions"
)
_HEALTH_API_PATH = f"{_API_PREFIX}/health" if _API_PREFIX else "/health"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = "user"
    content: Any = ""


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


class ChatCompletionResponseMessage(BaseModel):
    role: str = "assistant"
    content: str = ""


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionResponseMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "anubis-agent"
    name: str = ""


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


app = FastAPI(title="Anubis Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _get_run_lock() -> asyncio.Lock:
    lock = getattr(app.state, "run_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.run_lock = lock
    return lock


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    if content is None:
        return ""

    return str(content)


def _extract_latest_user_message(messages: list[ChatMessage]) -> str:
    fallback = ""

    for message in reversed(messages):
        content = _message_text(message.content).strip()
        if not content:
            continue

        if not fallback:
            fallback = content

        if str(message.role).lower() == "user":
            return content

    return fallback


def _short_text(value: Any, limit: int = 300) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text[:limit]


def _format_progress_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "progress"))
    message = str(event.get("message", "")).strip()
    state = event.get("state")
    prefix = f"[{event_type.upper()}]"
    if state:
        prefix += f" [{state}]"

    details: list[str] = []
    if event_type in {"tool_start", "tool_result", "tool_error", "tool_correction", "strategy_change"}:
        if event.get("tool"):
            details.append(f"tool={event['tool']}")
        if event.get("attempt"):
            details.append(f"attempt={event['attempt']}")
    if event_type in {"plan", "action", "verification"} and event.get("cycle"):
        details.append(f"cycle={event['cycle']}")
    if event_type == "intermediate_result" and event.get("result") is not None:
        details.append(_short_text(event["result"]))
    if event_type == "verification" and event.get("verification") is not None:
        details.append(_short_text(event["verification"]))
    if event_type in {"tool_result", "tool_error"} and event.get("result") is not None:
        details.append(_short_text(event["result"]))
    if event_type == "complete" and event.get("final_result") is not None:
        details.append(_short_text(event["final_result"], 800))
    if event_type == "blocked" and event.get("reason"):
        details.append(str(event["reason"]))

    detail_text = f" ({', '.join(details)})" if details else ""
    return f"{prefix} {message}{detail_text}\n\n"


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("final_result", "output", "reason"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value not in (None, ""):
                return json.dumps(value, ensure_ascii=False, default=str)
        return json.dumps(result, ensure_ascii=False, default=str)

    if result is None:
        return ""

    return str(result)


def _chat_completion_payload(
    model: str,
    content: str,
    completion_id: str,
    created: int,
) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=model,
        choices=[
            ChatCompletionChoice(
                message=ChatCompletionResponseMessage(
                    role="assistant",
                    content=content,
                ),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(),
    )


def _chat_completion_chunk(
    model: str,
    content: str,
    completion_id: str,
    created: int,
    *,
    finish_reason: str | None = None,
    include_role: bool = False,
) -> str:
    delta: dict[str, Any] = {}
    if include_role:
        delta["role"] = "assistant"
    if content:
        delta["content"] = content

    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _check_api_key(request: Request) -> None:
    if not API_AUTH_REQUIRED or not API_KEY:
        return

    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {API_KEY}"
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _stream_chat_completion(
    task: str,
    model: str,
    completion_id: str,
    created: int,
) -> Any:
    event_queue: queue.Queue[Any] = queue.Queue()

    def progress_callback(event: dict[str, Any]) -> None:
        event_queue.put({"kind": "progress", "event": event})

    def worker() -> None:
        try:
            result = run_agent_loop(task, progress_callback=progress_callback)
            event_queue.put({"kind": "result", "result": result})
        except Exception as exc:
            logger.exception("Streaming agent execution failed")
            event_queue.put({"kind": "error", "error": str(exc)})
        finally:
            event_queue.put(_STREAM_DONE)

    async def generator():
        emitted_role = False
        final_payload = ""
        final_emitted = False

        lock = _get_run_lock()
        async with lock:
            worker_thread = threading.Thread(target=worker, daemon=True)
            worker_thread.start()

            try:
                while True:
                    item = await asyncio.to_thread(event_queue.get)
                    if item is _STREAM_DONE:
                        break

                    kind = item.get("kind")
                    if kind == "progress":
                        text = _format_progress_event(item["event"])
                        yield _chat_completion_chunk(
                            model,
                            text,
                            completion_id,
                            created,
                            include_role=not emitted_role,
                        )
                        emitted_role = True
                        if item["event"].get("type") == "complete":
                            final_payload = str(item["event"].get("final_result", final_payload))
                            final_emitted = True
                        elif item["event"].get("type") == "blocked":
                            final_payload = _short_text(item["event"].get("final_result", ""), 1200)
                            final_emitted = True
                    elif kind == "result":
                        result = item["result"]
                        if not final_payload:
                            final_payload = _result_text(result)
                        if final_payload and not final_emitted:
                            yield _chat_completion_chunk(
                                model,
                                f"[FINAL] {final_payload}\n\n",
                                completion_id,
                                created,
                                include_role=not emitted_role,
                            )
                            emitted_role = True
                            final_emitted = True
                    elif kind == "error":
                        yield _chat_completion_chunk(
                            model,
                            f"[ERROR] {item['error']}\n\n",
                            completion_id,
                            created,
                            include_role=not emitted_role,
                        )
                        emitted_role = True

                yield _chat_completion_chunk(
                    model,
                    "",
                    completion_id,
                    created,
                    finish_reason="stop",
                    include_role=not emitted_role,
                )
                yield "data: [DONE]\n\n"
            finally:
                worker_thread.join(timeout=1)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if _HEALTH_API_PATH != "/health":
    app.add_api_route(_HEALTH_API_PATH, health, methods=["GET"])


@app.get(_MODELS_PATH, response_model=ModelListResponse)
async def list_models(request: Request) -> ModelListResponse:
    _check_api_key(request)

    now = int(time.time())
    return ModelListResponse(
        data=[
            ModelInfo(
                id=API_MODEL_ID,
                created=now,
                owned_by="anubis-agent",
                name=API_MODEL_NAME,
            )
        ]
    )


@app.get(_MODEL_DETAIL_PATH, response_model=ModelInfo)
async def get_model(model_id: str, request: Request) -> ModelInfo:
    _check_api_key(request)

    if model_id != API_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")

    return ModelInfo(
        id=API_MODEL_ID,
        created=int(time.time()),
        owned_by="anubis-agent",
        name=API_MODEL_NAME,
    )


@app.post(_CHAT_COMPLETIONS_PATH, response_model=ChatCompletionResponse)
async def chat_completions(payload: ChatCompletionRequest, request: Request) -> Any:
    _check_api_key(request)

    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list")

    task = _extract_latest_user_message(payload.messages)
    if not task:
        raise HTTPException(status_code=400, detail="messages must contain at least one user message")

    model = payload.model or API_MODEL_ID
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    logger.info("Processing OpenAI-compatible chat completion for model=%s", model)

    if payload.stream:
        return await _stream_chat_completion(task, model, completion_id, created)

    lock = getattr(request.app.state, "run_lock", None) or _get_run_lock()
    async with lock:
        result = await run_in_threadpool(run_agent_loop, task)

    content = _result_text(result)
    return _chat_completion_payload(model, content, completion_id, created)


def main() -> None:
    """Run the FastAPI server."""
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level=str(LOG_LEVEL).lower(),
    )


if __name__ == "__main__":
    main()
