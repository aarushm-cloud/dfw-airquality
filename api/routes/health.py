import time

from fastapi import APIRouter

from api.routes.grid import _cache as _grid_cache

router = APIRouter()

_STARTED_AT = time.time()


@router.get("/health", tags=["meta"])
def health() -> dict:
    """Cheap liveness + cache-warm probe for the frontend.

    Hit on every page load — must stay fast (no pipeline calls, no I/O).
    """
    return {
        "status": "ok",
        "cache_warm": _grid_cache.get("value") is not None,
        "uptime_seconds": int(time.time() - _STARTED_AT),
    }
