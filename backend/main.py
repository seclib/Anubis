import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agent, brain, health, local, notes, rag, skills
from backend.core.config import settings
from backend.core.logging import configure_logging


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
app.include_router(local.router)
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(skills.router, prefix="/api", tags=["skills"])
app.include_router(brain.router, prefix="/brain", tags=["brain"])
