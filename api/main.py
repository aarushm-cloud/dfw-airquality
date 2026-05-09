"""AERIA FastAPI backend — thin JSON wrapper around the existing pipeline.

Run from the project root:
    uvicorn api.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs

Optional startup flags (independent, mix and match):
  AERIA_WARMUP=1         — pre-populate the grid cache in a daemon thread.
  AERIA_PRELOAD_GRAPH=1  — pre-load the OSM walking graph in a daemon
                            thread (item 2 of Phase 5; first /api/route
                            otherwise pays the cold-load cost).
"""

import logging
import os
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.cells import router as cells_router
from api.routes.grid import get_cached_snapshot, router as grid_router
from api.routes.health import router as health_router
from api.routes.route import router as route_router
from api.routes.sensors import router as sensors_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
cors_logger = logging.getLogger("aeria.cors")
router_logger = logging.getLogger("aeria.router")

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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(sensors_router, prefix="/api")
app.include_router(grid_router, prefix="/api")
app.include_router(cells_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(route_router, prefix="/api")


def _warmup_pipeline() -> None:
    try:
        logger.info("AERIA_WARMUP=1 — priming grid cache in background...")
        get_cached_snapshot()
        logger.info("AERIA_WARMUP — grid cache primed.")
    except Exception as e:
        logger.warning("AERIA_WARMUP — pipeline prime failed: %s", e)


def _preload_walking_graph() -> None:
    # Imported here, not at module load, so a missing osmnx (or a slow
    # graph load) never blocks startup of the rest of the API.
    from engine.router import preload_graph

    try:
        router_logger.info("AERIA_PRELOAD_GRAPH=1 — loading walking graph in background...")
        t0 = time.time()
        preload_graph()
        router_logger.info(
            "AERIA_PRELOAD_GRAPH — walking graph ready in %.1fs.",
            time.time() - t0,
        )
    except Exception as e:
        # First /api/route call will retry the load synchronously through
        # the same find_routes codepath, so a preload failure is not fatal.
        router_logger.warning("AERIA_PRELOAD_GRAPH — preload failed: %s", e)


@app.on_event("startup")
def _maybe_warmup() -> None:
    if os.getenv("AERIA_WARMUP", "0") == "1":
        # Run in a daemon thread so startup doesn't block the event loop.
        # Endpoints stay responsive (e.g. /api/health) while the prime runs.
        threading.Thread(target=_warmup_pipeline, name="aeria-warmup", daemon=True).start()


@app.on_event("startup")
def _maybe_preload_graph() -> None:
    if os.getenv("AERIA_PRELOAD_GRAPH", "0") == "1":
        # Same daemon-thread pattern as _maybe_warmup. Walking-graph load
        # can take 60–180s on a cold cache, so doing this synchronously
        # would block uvicorn's event loop for that whole window.
        threading.Thread(
            target=_preload_walking_graph,
            name="aeria-preload-graph",
            daemon=True,
        ).start()


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "AERIA · DFW Air Quality API",
        "version": "0.1.0",
        "endpoints": [
            "/api/sensors",
            "/api/grid",
            "/api/cells/{zip}",
            "/api/health",
            "/api/route",
        ],
        "docs": "/docs",
    }
