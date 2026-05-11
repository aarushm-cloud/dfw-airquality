import time

from fastapi import APIRouter

from api.routes.grid import _TTL_SECONDS, _cache as _grid_cache

router = APIRouter()

_STARTED_AT = time.time()


@router.get("/health", tags=["meta"])
def health() -> dict:
    """Cheap liveness + cache-warm probe for the frontend.

    Hit on every page load — must stay fast (no pipeline calls, no I/O).
    """
    # Mirror grid.py's hit condition (present AND within TTL) so a stale
    # value doesn't falsely flip the frontend's READY signal.
    cache_warm = (
        _grid_cache.get("value") is not None
        and time.time() - _grid_cache.get("ts", 0) < _TTL_SECONDS
    )
    return {
        "status": "ok",
        "cache_warm": cache_warm,
        "uptime_seconds": int(time.time() - _STARTED_AT),
    }
