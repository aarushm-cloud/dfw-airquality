from functools import lru_cache

import numpy as np
import pandas as pd
import pgeocode
from fastapi import APIRouter, HTTPException
from uszipcode import SearchEngine

from config import BBOX
from data.ingestion.purpleair import classify_pm25

from api.routes.grid import get_cached_snapshot
from api.schemas.responses import CellAtResponse, CellResponse

router = APIRouter()

# Frontend's latLonToCell uses 30×30 cells over the same BBOX. Keep the row/col
# math here in lockstep so a zip-search hit selects exactly the cell the click
# handler would have selected.
_GRID_SIZE = 30

_nomi = pgeocode.Nominatim("us")
_search = SearchEngine(simple_zipcode=True)


def _zip_lookup(zip_code: str) -> tuple[float, float, str | None]:
    """Forward-geocode a US zip → (lat, lon, place_name). Raises 404 on miss."""
    result = _nomi.query_postal_code(zip_code)
    if pd.isna(result.latitude) or pd.isna(result.longitude):
        raise HTTPException(status_code=404, detail=f"Zip code {zip_code!r} not found.")
    place = result.place_name if pd.notna(result.place_name) else None
    return float(result.latitude), float(result.longitude), place


def _in_bbox(lat: float, lon: float) -> bool:
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


@lru_cache(maxsize=2048)
def _coords_to_zip_cached(lat_rounded: float, lon_rounded: float) -> tuple[str | None, str | None]:
    """Reverse-geocode rounded coords → (zip, city). Cached because the 30×30
    grid produces only ~900 distinct rounded inputs across the bbox."""
    results = _search.by_coordinates(lat_rounded, lon_rounded, radius=5, returns=1)
    if not results:
        return (None, None)
    rec = results[0]
    zip_code = rec.zipcode if rec.zipcode else None
    city = rec.major_city if getattr(rec, "major_city", None) else None
    return (zip_code, city)


def _latlon_to_cell(lat: float, lon: float) -> tuple[int | None, int | None, bool]:
    """Mirror of `latLonToCell` in web/src/world/bbox.ts. Half-open on north/east."""
    if lat < BBOX["south"] or lat >= BBOX["north"]:
        return (None, None, False)
    if lon < BBOX["west"] or lon >= BBOX["east"]:
        return (None, None, False)
    row = int(((lat - BBOX["south"]) * _GRID_SIZE) / (BBOX["north"] - BBOX["south"]))
    col = int(((lon - BBOX["west"]) * _GRID_SIZE) / (BBOX["east"] - BBOX["west"]))
    return (row, col, True)


# IMPORTANT: this route must be declared BEFORE /cells/{zip_code}, otherwise
# FastAPI matches "at" as a literal zip_code path param.
@router.get("/cells/at", response_model=CellAtResponse, tags=["cells"])
def get_cell_at(lat: float, lon: float) -> CellAtResponse:
    """Reverse-geocode a coordinate to its zip + neighborhood + grid cell.

    Used by the frontend after a cell click, since the click only knows row/col
    and needs a zip for display. Cached with 2-decimal rounding (~1.1 km).
    """
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    zip_code, city = _coords_to_zip_cached(lat_r, lon_r)
    row, col, in_bbox = _latlon_to_cell(lat, lon)
    return CellAtResponse(
        lat=lat,
        lon=lon,
        zip=zip_code,
        neighborhood=city,
        row=row,
        col=col,
        in_bbox=in_bbox,
    )


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
