"""AERIA FastAPI backend — thin JSON wrapper around the existing pipeline.

Run from the project root:
    uvicorn api.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs

Optional: set AERIA_WARMUP=1 before launch to pre-populate the grid cache
in a background thread at startup, so the first user request is instant.
"""

import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.cells import router as cells_router
from api.routes.grid import get_cached_snapshot, router as grid_router
from api.routes.health import router as health_router
from api.routes.sensors import router as sensors_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
cors_logger = logging.getLogger("aeria.cors")

# Local Vite dev server origins — always permitted so a misconfigured deploy
# env can never break local development.
DEV_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def resolve_cors_origins() -> list[str]:
    """Build the CORS allowlist from dev defaults + the AERIA_CORS_ORIGINS env var.

    AERIA_CORS_ORIGINS is a comma-separated list of additional origins (e.g. the
    production frontend at https://aeria.vercel.app). Dev defaults are always
    included; duplicates are dropped while preserving order.
    """
    raw = os.environ.get("AERIA_CORS_ORIGINS", "")
    extras = [o.strip() for o in raw.split(",") if o.strip()]
    origins = list(dict.fromkeys([*DEV_CORS_ORIGINS, *extras]))
    cors_logger.info("[cors] active origins: %s", origins)
    return origins


app = FastAPI(
    title="AERIA · DFW Air Quality API",
    description="JSON wrapper around the DFW air quality pipeline (PurpleAir + OpenAQ + IDW + traffic/wind adjustment).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=resolve_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(sensors_router, prefix="/api")
app.include_router(grid_router, prefix="/api")
app.include_router(cells_router, prefix="/api")
app.include_router(health_router, prefix="/api")


def _warmup_pipeline() -> None:
    try:
        logger.info("AERIA_WARMUP=1 — priming grid cache in background...")
        get_cached_snapshot()
        logger.info("AERIA_WARMUP — grid cache primed.")
    except Exception as e:
        logger.warning("AERIA_WARMUP — pipeline prime failed: %s", e)


@app.on_event("startup")
def _maybe_warmup() -> None:
    if os.getenv("AERIA_WARMUP", "0") == "1":
        # Run in a daemon thread so startup doesn't block the event loop.
        # Endpoints stay responsive (e.g. /api/health) while the prime runs.
        threading.Thread(target=_warmup_pipeline, name="aeria-warmup", daemon=True).start()


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "AERIA · DFW Air Quality API",
        "version": "0.1.0",
        "endpoints": ["/api/sensors", "/api/grid", "/api/cells/{zip}", "/api/health"],
        "docs": "/docs",
    }
