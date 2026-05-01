from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pgeocode
from fastapi import APIRouter, HTTPException

from config import BBOX
from data.ingestion.purpleair import classify_pm25

from api.routes.grid import get_cached_snapshot
from api.schemas.responses import CellResponse

router = APIRouter()

_nomi = pgeocode.Nominatim("us")


def _zip_lookup(zip_code: str) -> tuple[float, float, str | None]:
    """Forward-geocode a US zip → (lat, lon, place_name). Raises 404 on miss."""
    result = _nomi.query_postal_code(zip_code)
    if pd.isna(result.latitude) or pd.isna(result.longitude):
        raise HTTPException(status_code=404, detail=f"Zip code {zip_code!r} not found.")
    place = result.place_name if pd.notna(result.place_name) else None
    return float(result.latitude), float(result.longitude), place


def _in_bbox(lat: float, lon: float) -> bool:
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


@router.get("/cells/{zip_code}", response_model=CellResponse, tags=["cells"])
def get_cell(zip_code: str) -> CellResponse:
    """Look up the nearest grid cell for a US zip code and return its PM2.5.

    Uses the same cached pipeline snapshot as /api/grid, so calls are fast
    once the grid is warm.
    """
    lat, lon, place = _zip_lookup(zip_code)

    if not _in_bbox(lat, lon):
        raise HTTPException(
            status_code=404,
            detail=f"Zip code {zip_code} ({lat:.3f}, {lon:.3f}) is outside the Dallas bounding box.",
        )

    try:
        snap = get_cached_snapshot()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Pipeline failure: {e}")

    lat_arr = snap.lats_2d[:, 0]
    lon_arr = snap.lons_2d[0, :]
    i = int(np.argmin(np.abs(lat_arr - lat)))
    j = int(np.argmin(np.abs(lon_arr - lon)))

    pm25 = float(snap.grid[i, j])
    confidence = float(snap.confidence[i, j])

    return CellResponse(
        zip=zip_code,
        lat=lat,
        lon=lon,
        cell_lat=float(lat_arr[i]),
        cell_lon=float(lon_arr[j]),
        cell_i=i,
        cell_j=j,
        pm25=pm25,
        aqi_category=classify_pm25(pm25),
        confidence=confidence,
        neighborhood=place,
        timestamp=snap.timestamp,
    )
