import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agent, brain, desktop, health, local, notes, production, rag, skills
from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.watcher.markdown_watcher import start_observer, stop_observer


configure_logging()
logger = logging.getLogger("anubis.api")
app = FastAPI(title="Anubis Desktop OS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def local_only(request: Request, call_next):  # noqa: ANN001
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        logger.warning("blocked non-local request host=%s path=%s", host, request.url.path)
        return JSONResponse(status_code=403, content={"detail": "Local requests only"})

    logger.info("%s %s", request.method, request.url.path)
    return await call_next(request)


app.include_router(health.router)
app.include_router(production.router, tags=["production"])
app.include_router(desktop.router, tags=["desktop"])
app.include_router(local.router)
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(skills.router, prefix="/api", tags=["skills"])
app.include_router(brain.router, prefix="/brain", tags=["brain"])


@app.on_event("startup")
async def startup() -> None:
    if not settings.enable_watcher:
        return
    try:
        app.state.vault_observer = start_observer()
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("vault watcher disabled after startup failure: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    observer = getattr(app.state, "vault_observer", None)
    if observer is not None:
        stop_observer(observer)
        app.state.vault_observer = None
