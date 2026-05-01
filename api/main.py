"""AERIA FastAPI backend — thin JSON wrapper around the existing pipeline.

Run from the project root:
    uvicorn api.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.cells import router as cells_router
from api.routes.grid import router as grid_router
from api.routes.sensors import router as sensors_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AERIA · DFW Air Quality API",
    description="JSON wrapper around the DFW air quality pipeline (PurpleAir + OpenAQ + IDW + traffic/wind adjustment).",
    version="0.1.0",
)

# Vite dev server runs on 5173. Allow it (and a couple of common alternatives)
# during local development. Tighten this for any deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(sensors_router, prefix="/api")
app.include_router(grid_router, prefix="/api")
app.include_router(cells_router, prefix="/api")


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "AERIA · DFW Air Quality API",
        "version": "0.1.0",
        "endpoints": ["/api/sensors", "/api/grid", "/api/cells/{zip}"],
        "docs": "/docs",
    }
