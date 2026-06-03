"""Deny-by-default network isolation and proxy control for ANUBIS agents."""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class NetworkIsolationViolation(PermissionError):
    """Raised when a network request violates isolation policy."""


class NetworkDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkRequestMethod(StrEnum):
    GET = "GET"
    POST = "POST"


@dataclass(frozen=True)
class NetworkRequest:
    task_id: str
    url: str
    method: NetworkRequestMethod | str = NetworkRequestMethod.GET
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None

    @property
    def method_value(self) -> str:
        return self.method.value if isinstance(self.method, NetworkRequestMethod) else str(self.method).upper()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "method": self.method_value,
            "headers": dict(self.headers),
            "body_bytes": len(self.body or b""),
        }


@dataclass(frozen=True)
class NetworkProxyResponse:
    success: bool
    url: str
    status_code: int | None = None
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "url": self.url,
            "status_code": self.status_code,
            "body": self.body,
            "headers": dict(self.headers),
            "error": self.error,
        }


@dataclass(frozen=True)
class NetworkAuditEntry:
    task_id: str
    url: str
    host: str | None
    decision: NetworkDecision
    reason: str
    method: str = "GET"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "host": self.host,
            "decision": self.decision.value,
            "reason": self.reason,
            "method": self.method,
            "created_at": self.created_at.isoformat(),
        }


class NetworkAuditLogger:
    def __init__(self, audit_log_path: str | Path | None = None) -> None:
        self.audit_log_path = Path(audit_log_path).resolve() if audit_log_path else None
        self._entries: list[NetworkAuditEntry] = []

    def record(self, entry: NetworkAuditEntry) -> NetworkAuditEntry:
        self._entries.append(entry)
        if self.audit_log_path is not None:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
        return entry

    def entries(self) -> tuple[NetworkAuditEntry, ...]:
        return tuple(self._entries)


@dataclass(frozen=True)
class DomainAllowlist:
    domains: frozenset[str] = frozenset()

    def allows(self, host: str) -> bool:
        normalized = _normalize_host(host)
        for domain in self.domains:
            allowed = _normalize_host(domain)
            if normalized == allowed or normalized.endswith(f".{allowed}"):
                return True
        return False


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int = 10
    window_seconds: float = 60.0


class NetworkRateLimiter:
    def __init__(self, rule: RateLimitRule | None = None) -> None:
        self.rule = rule or RateLimitRule()
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, task_id: str, host: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        key = (task_id, _normalize_host(host))
        bucket = self._requests[key]
        while bucket and current - bucket[0] > self.rule.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.rule.max_requests:
            return False
        bucket.append(current)
        return True


@dataclass(frozen=True)
class NetworkIsolationConfig:
    allow_network: bool = False
    allowlist: DomainAllowlist = field(default_factory=DomainAllowlist)
    rate_limit: RateLimitRule = field(default_factory=RateLimitRule)
    audit_log_path: str | None = None
    timeout_seconds: float = 5.0
    max_response_chars: int = 12000
    resolve_dns: bool = True


Transport = Callable[[NetworkRequest, float], NetworkProxyResponse]


class NetworkPolicy:
    """Validates outbound requests before proxy execution."""

    def __init__(self, config: NetworkIsolationConfig | None = None, *, resolver: Callable[[str], tuple[str, ...]] | None = None) -> None:
        self.config = config or NetworkIsolationConfig()
        self.resolver = resolver or _resolve_host
        self.rate_limiter = NetworkRateLimiter(self.config.rate_limit)

    def validate(self, request: NetworkRequest) -> tuple[bool, str, str | None]:
        if not self.config.allow_network:
            return False, "network access disabled by default", None
        if not request.task_id.strip():
            return False, "task_id is required", None

        parsed = urlparse(request.url)
        if parsed.scheme not in {"http", "https"}:
            return False, "only http/https proxy requests are allowed", parsed.hostname
        host = parsed.hostname
        if not host:
            return False, "request host is required", None
        normalized_host = _normalize_host(host)
        if _is_sensitive_host(normalized_host):
            return False, "sensitive endpoint is blocked", normalized_host
        if not self.config.allowlist.allows(normalized_host):
            return False, "domain is not allowlisted", normalized_host
        if self.config.resolve_dns:
            for address in self.resolver(normalized_host):
                if _is_sensitive_address(address):
                    return False, "resolved address is blocked", normalized_host
        if not self.rate_limiter.allow(request.task_id, normalized_host):
            return False, "network rate limit exceeded", normalized_host
        return True, "approved", normalized_host


class ProxyController:
    """Controlled proxy: validates, logs, rate-limits, then performs request."""

    def __init__(
        self,
        config: NetworkIsolationConfig | None = None,
        *,
        transport: Transport | None = None,
        audit_logger: NetworkAuditLogger | None = None,
        policy: NetworkPolicy | None = None,
    ) -> None:
        self.config = config or NetworkIsolationConfig()
        self.audit_logger = audit_logger or NetworkAuditLogger(self.config.audit_log_path)
        self.policy = policy or NetworkPolicy(self.config)
        self.transport = transport or self._default_transport

    def request(self, request: NetworkRequest) -> NetworkProxyResponse:
        allowed, reason, host = self.policy.validate(request)
        decision = NetworkDecision.ALLOW if allowed else NetworkDecision.DENY
        self.audit_logger.record(
            NetworkAuditEntry(
                task_id=request.task_id,
                url=request.url,
                host=host,
                decision=decision,
                reason=reason,
                method=request.method_value,
            )
        )
        if not allowed:
            return NetworkProxyResponse(success=False, url=request.url, error=reason)
        return self.transport(request, self.config.timeout_seconds)

    def get(self, task_id: str, url: str, headers: dict[str, str] | None = None) -> NetworkProxyResponse:
        return self.request(NetworkRequest(task_id=task_id, url=url, method=NetworkRequestMethod.GET, headers=dict(headers or {})))

    def audit_entries(self) -> tuple[NetworkAuditEntry, ...]:
        return self.audit_logger.entries()

    def _default_transport(self, request: NetworkRequest, timeout: float) -> NetworkProxyResponse:
        urllib_request = urllib.request.Request(
            request.url,
            data=request.body,
            headers=request.headers,
            method=request.method_value,
        )
        try:
            with urllib.request.urlopen(urllib_request, timeout=timeout) as response:
                body = response.read(self.config.max_response_chars + 1).decode("utf-8", errors="replace")
                return NetworkProxyResponse(
                    success=200 <= response.status < 400,
                    url=request.url,
                    status_code=response.status,
                    body=body[: self.config.max_response_chars],
                    headers={key: value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            return NetworkProxyResponse(success=False, url=request.url, status_code=exc.code, error=str(exc))
        except Exception as exc:
            return NetworkProxyResponse(success=False, url=request.url, error=f"{exc.__class__.__name__}: {exc}")


def _normalize_host(host: str) -> str:
    return host.strip().strip(".").lower()


def _resolve_host(host: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return ()
    return tuple(sorted({info[4][0] for info in infos}))


def _is_sensitive_host(host: str) -> bool:
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return True
    try:
        return _is_sensitive_address(host)
    except ValueError:
        return False


def _is_sensitive_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


__all__ = [
    "DomainAllowlist",
    "NetworkAuditEntry",
    "NetworkAuditLogger",
    "NetworkDecision",
    "NetworkIsolationConfig",
    "NetworkIsolationViolation",
    "NetworkPolicy",
    "NetworkProxyResponse",
    "NetworkRateLimiter",
    "NetworkRequest",
    "NetworkRequestMethod",
    "ProxyController",
    "RateLimitRule",
]
