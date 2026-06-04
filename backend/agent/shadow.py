from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from anubis.core.agent_core import AgentCore, AgentCoreRequest


logger = logging.getLogger("anubis.agent.shadow")


@dataclass(frozen=True)
class ShadowRequest:
    prompt: str
    active_response: dict[str, Any]
    context: str = ""
    source: str = "http-agent"
    request_id: str = field(default_factory=lambda: uuid4().hex)


class ShadowAgentRunner:
    """Runs the new Agent Core beside the active system without user impact."""

    def __init__(
        self,
        *,
        core: AgentCore | None = None,
        log_path: Path | str = Path("state/agent_shadow.jsonl"),
        enabled: bool = True,
    ) -> None:
        self.core = core or AgentCore()
        self.log_path = Path(log_path)
        self.enabled = enabled
        self._lock = Lock()

    def submit(self, request: ShadowRequest) -> None:
        if not self.enabled:
            return
        Thread(target=self._run_and_log, args=(request,), daemon=True).start()

    def run_inline(self, request: ShadowRequest) -> None:
        if not self.enabled:
            return
        self._run_and_log(request)

    def _run_and_log(self, request: ShadowRequest) -> None:
        try:
            result = self.core.run(
                AgentCoreRequest(
                    prompt=request.prompt,
                    context=request.context,
                    request_id=request.request_id,
                    metadata={"source": request.source, "mode": "shadow"},
                )
            )
            record = _record(request, shadow_result=result.to_dict())
        except Exception as exc:  # pragma: no cover - shadow must never break active traffic
            logger.warning("shadow agent execution failed request_id=%s error=%s", request.request_id, exc)
            record = _record(
                request,
                shadow_result={
                    "request_id": request.request_id,
                    "ok": False,
                    "confidence": 0.0,
                    "answer": "",
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "events": [],
                },
            )
        self._write(record)

    def _write(self, record: dict[str, Any]) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, sort_keys=True, default=str)
            with self._lock:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{line}\n")
        except Exception as exc:  # pragma: no cover - logging must never break active traffic
            logger.warning("failed to write shadow agent log path=%s error=%s", self.log_path, exc)


def _record(request: ShadowRequest, *, shadow_result: dict[str, Any]) -> dict[str, Any]:
    active_answer = str(request.active_response.get("answer") or "")
    shadow_answer = str(shadow_result.get("answer") or "")
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "shadow",
        "request_id": request.request_id,
        "source": request.source,
        "prompt_chars": len(request.prompt),
        "active": _active_payload(request.active_response),
        "shadow": shadow_result,
        "summary": {
            "active_answer_chars": len(active_answer),
            "shadow_answer_chars": len(shadow_answer),
            "shadow_ok": bool(shadow_result.get("ok")),
            "shadow_confidence": float(shadow_result.get("confidence") or 0.0),
            "answers_exact_match": active_answer.strip() == shadow_answer.strip(),
        },
    }


def _active_payload(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": response.get("answer", ""),
        "chunks_used_count": len(response.get("chunks_used") or []),
        "skills_used_count": len(response.get("skills_used") or []),
        "actions_count": len(response.get("actions") or []),
        "memory_path": response.get("memory_path"),
    }


__all__ = ["ShadowAgentRunner", "ShadowRequest"]
