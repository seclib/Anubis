from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4

from anubis.core.session import SessionRuntime


@dataclass(frozen=True)
class AgentCoreRequest:
    prompt: str
    context: str = ""
    request_id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentCoreResult:
    request_id: str
    answer: str
    confidence: float
    ok: bool
    duration_ms: int
    events: list[dict[str, Any]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentCore:
    """New public Agent Core facade used for zero-downtime migration.

    Phase 1 runs this in shadow mode only. It must not mutate user-visible
    response behavior; callers decide whether to expose the result.
    """

    def __init__(self, runtime: SessionRuntime | None = None) -> None:
        self.runtime = runtime or SessionRuntime()

    def run(self, request: AgentCoreRequest) -> AgentCoreResult:
        started = perf_counter()
        events: list[dict[str, Any]] = []
        answer = ""
        error: str | None = None
        ok = True
        try:
            for event in self.runtime.run(_task_text(request)):
                event_payload = {
                    "type": event.type,
                    "message": event.message,
                    "payload": dict(event.payload),
                }
                events.append(event_payload)
                if event.type == "session.done":
                    answer = str(event.payload.get("result") or "").strip()
                elif event.type == "error":
                    ok = False
                    error = str(event.payload.get("error") or event.message)
        except Exception as exc:
            ok = False
            error = f"{exc.__class__.__name__}: {exc}"

        return AgentCoreResult(
            request_id=request.request_id,
            answer=answer,
            confidence=_confidence(ok=ok, answer=answer, error=error, events=events),
            ok=ok,
            duration_ms=int((perf_counter() - started) * 1000),
            events=events,
            error=error,
        )


def _task_text(request: AgentCoreRequest) -> str:
    if not request.context.strip():
        return request.prompt
    return f"{request.prompt}\n\nContext:\n{request.context}"


def _confidence(*, ok: bool, answer: str, error: str | None, events: list[dict[str, Any]]) -> float:
    if error or not ok:
        return 0.0
    if not answer.strip():
        return 0.25
    if any(event["type"] in {"guardrail.triggered", "tool.error"} for event in events):
        return 0.55
    return 0.95


__all__ = ["AgentCore", "AgentCoreRequest", "AgentCoreResult"]
