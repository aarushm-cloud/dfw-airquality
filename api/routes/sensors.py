import time
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException

from data.ingestion.openaq import fetch_openaq
from data.ingestion.purpleair import fetch_sensors

from api.schemas.responses import FilteredSensor, SensorReading, SensorsResponse

router = APIRouter()

_TTL_SECONDS = 300
_cache: dict = {"ts": 0.0, "value": None}


def _fetch_combined() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (combined_kept, purpleair_dropped):
      combined_kept     — purpleair kept rows + all openaq rows, ready
                          for downstream consumers that want a single
                          frame.
      purpleair_dropped — quarantined purpleair rows; openaq has no
                          equivalent failure mode so this is purpleair-only.
    """
    purpleair_kept, purpleair_dropped = fetch_sensors()
    openaq_df = fetch_openaq()
    combined = pd.concat([purpleair_kept, openaq_df], ignore_index=True)
    return combined, purpleair_dropped


def get_cached_sensors() -> tuple[pd.DataFrame, pd.DataFrame]:
    now = time.time()
    if _cache["value"] is not None and now - _cache["ts"] < _TTL_SECONDS:
        return _cache["value"]
    pair = _fetch_combined()
    _cache["ts"] = now
    _cache["value"] = pair
    return pair


def _row_to_reading(row: pd.Series) -> SensorReading:
    raw = row.get("pm25_raw")
    return SensorReading(
        sensor_id=str(row["sensor_id"]),
        name=str(row["name"]) if pd.notna(row.get("name")) else "",
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        pm25=float(row["pm25"]),
        pm25_raw=float(raw) if pd.notna(raw) else None,
        epa_corrected=int(row.get("epa_corrected", 0) or 0),
        source=str(row.get("source", "unknown")),
    )


def _row_to_filtered(row: pd.Series) -> FilteredSensor:
    return FilteredSensor(
        sensor_id=str(row["sensor_id"]),
        name=str(row["name"]),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        pm25_raw=float(row["pm25_raw"]),
        reason=str(row["filter_reason"]),
    )


@router.get("/sensors", response_model=SensorsResponse, tags=["sensors"])
def get_sensors() -> SensorsResponse:
    """Live PM2.5 readings from PurpleAir + OpenAQ inside the Dallas bounding box.

    PurpleAir values are EPA-corrected at ingest. OpenAQ values are
    reference-grade and reported as-is. Cached for 5 minutes.
    """
    try:
        combined, filtered = get_cached_sensors()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream sensor fetch failed: {e}")

    return SensorsResponse(
        count=len(combined),
        timestamp=datetime.now(timezone.utc).isoformat(),
        sensors=[_row_to_reading(row) for _, row in combined.iterrows()],
        filtered_sensors=[_row_to_filtered(row) for _, row in filtered.iterrows()],
    )
