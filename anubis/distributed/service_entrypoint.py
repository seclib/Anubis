"""Deployment entrypoint for ANUBIS distributed services."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from anubis.distributed.company_runtime import AutonomousCompanyRuntime, CompanyRuntimeConfig


LOG_LEVEL = os.getenv("ANUBIS_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("anubis.distributed.service")


class ServiceState:
    def __init__(self, role: str) -> None:
        self.role = role
        self.started_at = time.time()
        self.ready = False
        self.stopping = False
        self.last_cycle: dict[str, Any] | None = None
        self.error: str | None = None

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.error is None else "degraded",
            "role": self.role,
            "ready": self.ready,
            "stopping": self.stopping,
            "uptime_seconds": round(time.time() - self.started_at, 3),
            "external_memory": {
                "redis_url_configured": bool(os.getenv("ANUBIS_REDIS_URL")),
                "qdrant_url_configured": bool(os.getenv("ANUBIS_QDRANT_URL")),
                "git_remote_configured": bool(os.getenv("ANUBIS_GIT_REMOTE")),
            },
            "last_cycle": self.last_cycle,
            "error": self.error,
        }


class HealthHandler(BaseHTTPRequestHandler):
    state: ServiceState

    def do_GET(self) -> None:
        if self.path not in {"/", "/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = self.state.health()
        status = 200 if self.path != "/ready" or self.state.ready else 503
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("health: " + fmt, *args)


def start_health_server(state: ServiceState, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("AnubisHealthHandler", (HealthHandler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("health server listening role=%s host=%s port=%s", state.role, host, port)
    return server


async def run_company_runtime(state: ServiceState) -> None:
    enabled = os.getenv("ANUBIS_COMPANY_RUNTIME_ENABLED", "false").lower() in {"1", "true", "yes"}
    interval = float(os.getenv("ANUBIS_COMPANY_CYCLE_INTERVAL_SECONDS", "60"))
    runtime = AutonomousCompanyRuntime(config=CompanyRuntimeConfig(cycle_interval_seconds=interval))
    state.ready = True
    logger.info("company runtime role ready enabled=%s interval=%s", enabled, interval)

    if not enabled:
        while not state.stopping:
            await asyncio.sleep(1)
        return

    while not state.stopping:
        result = await runtime.run_once()
        state.last_cycle = result.to_dict()
        await asyncio.sleep(interval)


async def run_stateless_role(state: ServiceState) -> None:
    state.ready = True
    logger.info("stateless distributed role ready role=%s", state.role)
    while not state.stopping:
        await asyncio.sleep(1)


async def amain() -> None:
    parser = argparse.ArgumentParser(description="ANUBIS distributed deployment service")
    parser.add_argument(
        "--role",
        required=True,
        choices=[
            "api-gateway",
            "company-runtime",
            "orchestrator",
            "planner",
            "executor",
            "reviewer",
            "tool-runner",
        ],
    )
    parser.add_argument("--host", default=os.getenv("ANUBIS_HEALTH_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ANUBIS_HEALTH_PORT", "8080")))
    args = parser.parse_args()

    state = ServiceState(args.role)
    server = start_health_server(state, args.host, args.port)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, setattr, state, "stopping", True)

    try:
        if args.role == "company-runtime":
            await run_company_runtime(state)
        else:
            await run_stateless_role(state)
    except Exception as exc:
        state.error = f"{exc.__class__.__name__}: {exc}"
        logger.exception("distributed service failed role=%s", args.role)
        raise
    finally:
        state.stopping = True
        server.shutdown()
        server.server_close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
