"""Structured inter-agent communication bus."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

AGENT_MESSAGE_TYPES = {
    "task",
    "result",
    "context",
    "coordination",
    "status",
    "error",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_bus(memory: dict[str, Any]) -> dict[str, Any]:
    bus = memory.get("agent_communication")
    if not isinstance(bus, dict):
        bus = {}
        memory["agent_communication"] = bus

    if not isinstance(bus.get("queue"), list):
        bus["queue"] = []
    if not isinstance(bus.get("history"), list):
        bus["history"] = []
    if not isinstance(bus.get("inbox"), dict):
        bus["inbox"] = {}
    if not isinstance(bus.get("stats"), dict):
        bus["stats"] = {
            "sent": 0,
            "delivered": 0,
            "pending": 0,
        }

    bus["stats"]["pending"] = len(bus["queue"])
    return bus


def create_agent_message(
    *,
    sender: str,
    recipient: str,
    message_type: str,
    payload: Any,
    task_id: str | None = None,
    priority: int = 50,
    context: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    normalized_type = message_type if message_type in AGENT_MESSAGE_TYPES else "context"
    return {
        "id": str(uuid4()),
        "correlation_id": correlation_id,
        "task_id": task_id,
        "sender": sender,
        "recipient": recipient,
        "type": normalized_type,
        "priority": int(priority),
        "payload": payload,
        "context": context or {},
        "status": "queued",
        "created_at": _now_iso(),
        "delivered_at": None,
    }


def enqueue_agent_message(
    memory: dict[str, Any],
    *,
    sender: str,
    recipient: str,
    message_type: str,
    payload: Any,
    task_id: str | None = None,
    priority: int = 50,
    context: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    bus = _ensure_bus(memory)
    message = create_agent_message(
        sender=sender,
        recipient=recipient,
        message_type=message_type,
        payload=payload,
        task_id=task_id,
        priority=priority,
        context=context,
        correlation_id=correlation_id,
    )
    bus["queue"].append(message)
    bus["queue"].sort(key=lambda item: (-int(item.get("priority", 50)), item.get("created_at", "")))
    bus["history"].append({**message, "event": "queued"})
    bus["stats"]["sent"] = int(bus["stats"].get("sent", 0)) + 1
    bus["stats"]["pending"] = len(bus["queue"])
    return message


def dequeue_agent_messages(
    memory: dict[str, Any],
    *,
    recipient: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    bus = _ensure_bus(memory)
    delivered: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    max_items = limit if limit is not None and limit >= 0 else None

    for message in bus["queue"]:
        matches_recipient = recipient is None or message.get("recipient") in {recipient, "*"}
        if matches_recipient and (max_items is None or len(delivered) < max_items):
            delivered_message = {
                **message,
                "status": "delivered",
                "delivered_at": _now_iso(),
            }
            delivered.append(delivered_message)
            bus["history"].append({**delivered_message, "event": "delivered"})
            inbox = bus["inbox"].setdefault(str(message.get("recipient", "unknown")), [])
            inbox.append(delivered_message)
            continue

        remaining.append(message)

    bus["queue"] = remaining
    bus["stats"]["delivered"] = int(bus["stats"].get("delivered", 0)) + len(delivered)
    bus["stats"]["pending"] = len(bus["queue"])
    return delivered


def share_agent_result(
    memory: dict[str, Any],
    *,
    sender: str,
    result: Any,
    recipient: str = "*",
    phase: str = "",
    success: bool = True,
) -> dict[str, Any]:
    return enqueue_agent_message(
        memory,
        sender=sender,
        recipient=recipient,
        message_type="result",
        payload={
            "phase": phase,
            "success": success,
            "result": result,
        },
        priority=60 if success else 90,
    )


def send_agent_task(
    memory: dict[str, Any],
    *,
    sender: str,
    recipient: str,
    task: str,
    phase: str,
    priority: int = 50,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return enqueue_agent_message(
        memory,
        sender=sender,
        recipient=recipient,
        message_type="task",
        payload={
            "task": task,
            "phase": phase,
        },
        priority=priority,
        context=context,
    )


def broadcast_agent_context(
    memory: dict[str, Any],
    *,
    sender: str,
    context: dict[str, Any],
    recipient: str = "*",
    priority: int = 40,
) -> dict[str, Any]:
    return enqueue_agent_message(
        memory,
        sender=sender,
        recipient=recipient,
        message_type="context",
        payload=context,
        priority=priority,
    )


def communication_context(memory: dict[str, Any], limit: int = 8) -> str:
    bus = _ensure_bus(memory)
    history = bus.get("history", [])
    if not history:
        return "No inter-agent communication yet."

    lines: list[str] = []
    for message in history[-limit:]:
        sender = message.get("sender", "unknown")
        recipient = message.get("recipient", "unknown")
        message_type = message.get("type", "context")
        status = message.get("status", "unknown")
        payload = str(message.get("payload", ""))[:500]
        lines.append(f"- {sender} -> {recipient} [{message_type}/{status}]: {payload}")

    return "\n".join(lines)


def communication_snapshot(memory: dict[str, Any]) -> dict[str, Any]:
    bus = _ensure_bus(memory)
    return {
        "queue": list(bus["queue"]),
        "history": list(bus["history"]),
        "inbox": dict(bus["inbox"]),
        "stats": dict(bus["stats"]),
    }


__all__ = [
    "AGENT_MESSAGE_TYPES",
    "broadcast_agent_context",
    "communication_context",
    "communication_snapshot",
    "create_agent_message",
    "dequeue_agent_messages",
    "enqueue_agent_message",
    "send_agent_task",
    "share_agent_result",
]
