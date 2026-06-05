def local_only_middleware(request: dict) -> dict:
    return {"allowed": True, "request": dict(request), "reason": "local-only API facade"}


__all__ = ["local_only_middleware"]
