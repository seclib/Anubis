"""OpenAI-compatible HTTP server for Open WebUI."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from agent.loop import run_agent_loop
from agent.streaming import (
    agent_event_payload,
    format_progress_event,
    format_sse_event,
    short_text,
)
from config import API_HOST, API_KEY, API_MODEL_ID, API_MODEL_NAME, API_PORT

logger = logging.getLogger(__name__)
_STREAM_DONE = object()


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

    return str(content)


def _messages_to_task(messages: list[dict[str, Any]]) -> str:
    system_messages: list[str] = []
    transcript: list[str] = []
    latest_user_message = ""

    for message in messages:
        role = str(message.get("role", "user"))
        content = _message_text(message.get("content", ""))
        if not content.strip():
            continue

        if role == "system":
            system_messages.append(content.strip())
            continue

        transcript.append(f"[{role}] {content.strip()}")
        if role == "user":
            latest_user_message = content.strip()

    if not transcript and latest_user_message:
        return latest_user_message

    task_parts: list[str] = []
    if system_messages:
        task_parts.append("System instructions:")
        task_parts.append("\n".join(system_messages))

    if transcript:
        task_parts.append("Conversation context:")
        task_parts.append("\n".join(transcript))

    if latest_user_message:
        task_parts.append("Latest user request:")
        task_parts.append(latest_user_message)

    return "\n\n".join(task_parts).strip() or "Respond to the user request."


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _unauthorized(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(_json_bytes({"error": {"message": "Unauthorized"}}))


def _check_api_key(handler: BaseHTTPRequestHandler) -> bool:
    if not API_KEY:
        return True

    auth_header = handler.headers.get("Authorization", "")
    expected = f"Bearer {API_KEY}"
    if auth_header == expected:
        return True

    _unauthorized(handler)
    return False


class OpenAICompatibleHandler(BaseHTTPRequestHandler):
    server_version = "AnubisOpenAICompatible/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if not content_length:
            return {}

        try:
            raw_body = self.rfile.read(int(content_length))
            if not raw_body:
                return {}
            data = json.loads(raw_body.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _chat_completion_payload(
        self,
        model: str,
        content: str,
        completion_id: str,
        created: int,
    ) -> dict[str, Any]:
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    def _send_streaming_completion(
        self,
        model: str,
        task: str,
        completion_id: str,
        created: int,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        event_queue: queue.Queue[Any] = queue.Queue()

        def emit_chunk(content: str, finish_reason: str | None = None, include_role: bool = False) -> None:
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
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

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

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        final_payload = ""
        emitted_role = False
        final_emitted = False

        try:
            while True:
                item = event_queue.get()
                if item is _STREAM_DONE:
                    break

                kind = item.get("kind")
                if kind == "progress":
                    text = format_progress_event(item["event"])
                    emit_chunk(text, include_role=not emitted_role)
                    emitted_role = True
                    if item["event"].get("type") == "complete":
                        final_payload = str(item["event"].get("final_result", final_payload))
                        final_emitted = True
                    elif item["event"].get("type") == "blocked":
                        final_payload = short_text(item["event"].get("final_result", ""), 1200)
                        final_emitted = True
                elif kind == "result":
                    result = item["result"]
                    if not final_payload:
                        final_payload = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                    if final_payload and not final_emitted:
                        emit_chunk(
                            f"[FINAL] {final_payload}\n\n",
                            include_role=not emitted_role,
                        )
                        emitted_role = True
                        final_emitted = True
                elif kind == "error":
                    emit_chunk(
                        f"[ERROR] {item['error']}\n\n",
                        include_role=not emitted_role,
                    )
                    emitted_role = True

            emit_chunk("", finish_reason="stop", include_role=not emitted_role)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        finally:
            worker_thread.join(timeout=1)

    def _send_agent_event_stream(self, task: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        event_queue: queue.Queue[Any] = queue.Queue()

        def progress_callback(event: dict[str, Any]) -> None:
            event_queue.put({"kind": "progress", "event": event})

        def worker() -> None:
            try:
                result = run_agent_loop(task, progress_callback=progress_callback)
                event_queue.put({"kind": "result", "result": result})
            except Exception as exc:
                logger.exception("Structured streaming agent execution failed")
                event_queue.put({"kind": "error", "error": str(exc)})
            finally:
                event_queue.put(_STREAM_DONE)

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()
        sequence = 0

        try:
            while True:
                item = event_queue.get()
                if item is _STREAM_DONE:
                    break

                sequence += 1
                kind = item.get("kind")
                if kind == "progress":
                    payload = agent_event_payload(item["event"], sequence)
                    event_text = format_sse_event("agent_progress", payload, event_id=sequence)
                elif kind == "result":
                    payload = {"sequence": sequence, "result": item["result"]}
                    event_text = format_sse_event("agent_result", payload, event_id=sequence)
                elif kind == "error":
                    payload = {"sequence": sequence, "error": item["error"]}
                    event_text = format_sse_event("agent_error", payload, event_id=sequence)
                else:
                    continue

                self.wfile.write(event_text.encode("utf-8"))
                self.wfile.flush()

            sequence += 1
            self.wfile.write(
                format_sse_event("agent_done", {"sequence": sequence}, event_id=sequence).encode("utf-8")
            )
            self.wfile.flush()
        finally:
            worker_thread.join(timeout=1)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        if path == "/v1/models":
            if not _check_api_key(self):
                return

            now = int(time.time())
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": API_MODEL_ID,
                            "object": "model",
                            "created": now,
                            "owned_by": "anubis-agent",
                            "name": API_MODEL_NAME,
                        }
                    ],
                },
            )
            return

        self._send_json(404, {"error": {"message": f"Unknown endpoint: {path}"}})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/v1/chat/completions", "/v1/agent/stream"}:
            self._send_json(404, {"error": {"message": f"Unknown endpoint: {path}"}})
            return

        if not _check_api_key(self):
            return

        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": {"message": "Invalid JSON body"}})
            return

        if path == "/v1/agent/stream":
            task = str(payload.get("task") or "").strip()
            messages = payload.get("messages", [])
            if not task and isinstance(messages, list) and messages:
                task = _messages_to_task(messages)
            if not task:
                self._send_json(400, {"error": {"message": "task or messages must contain a request"}})
                return
            self._send_agent_event_stream(task)
            return

        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            self._send_json(400, {"error": {"message": "messages must be a non-empty list"}})
            return

        model = str(payload.get("model") or API_MODEL_ID)
        stream = bool(payload.get("stream", False))
        task = _messages_to_task(messages)

        logger.info("Processing OpenAI-compatible chat completion for model=%s", model)
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        if stream:
            self._send_streaming_completion(model, task, completion_id, created)
            return

        result = run_agent_loop(task)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

        self._send_json(
            200,
            self._chat_completion_payload(model, content, completion_id, created),
        )


def run_openai_compatible_server(
    host: str = API_HOST,
    port: int = API_PORT,
) -> None:
    """Start the local OpenAI-compatible API server."""
    server = ThreadingHTTPServer((host, port), OpenAICompatibleHandler)
    logger.info("OpenAI-compatible API listening on http://%s:%s/v1", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping OpenAI-compatible API server")
    finally:
        server.server_close()


__all__ = ["run_openai_compatible_server"]
