from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from anubis_memory_sdk import ShortTermMemory
from anubis_tools import create_default_registry

from anubis_ai_core.agent.state_manager import AgentStateManager
from anubis_ai_core.api.routes import router
from anubis_ai_core.core.config import Settings
from anubis_ai_core.core.logging import configure_logging
from anubis_ai_core.core.middleware import RequestContextMiddleware
from anubis_ai_core.orchestrator.session_manager import OrchestrationSessionManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.short_term_memory = ShortTermMemory()
    app.state.agent_state_manager = AgentStateManager()
    app.state.orchestration_session_manager = OrchestrationSessionManager()
    app.state.tool_registry = create_default_registry(workspace_root=str(settings.allowed_workspace))
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Anubis AI Core", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    return app
