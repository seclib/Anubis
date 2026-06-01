from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from anubis_rag.api.routes import router
from anubis_rag.core.config import Settings
from anubis_rag.core.logging import configure_logging
from anubis_rag.core.middleware import RequestContextMiddleware
from anubis_rag.storage.qdrant_store import QdrantVectorStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.vector_store = QdrantVectorStore(settings)
    await app.state.vector_store.ensure_collection()
    yield
    await app.state.vector_store.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Anubis RAG", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    return app
