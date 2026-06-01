from __future__ import annotations

from fastapi import FastAPI

from anubis_kernel.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Anubis Kernel", version="0.1.0")
    app.include_router(router)
    return app
