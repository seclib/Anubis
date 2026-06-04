from fastapi import APIRouter

from backend.core.config import settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def live() -> dict[str, str]:
    return health()


@router.get("/health/ready")
def ready() -> dict[str, object]:
    return {
        "status": "ready",
        "vault_path": str(settings.vault_path),
        "qdrant_url": settings.qdrant_url,
        "qdrant_collection": settings.qdrant_collection,
    }
