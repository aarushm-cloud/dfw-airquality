import time
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException

from data.ingestion.openaq import fetch_openaq
from data.ingestion.purpleair import fetch_sensors

from api.schemas.responses import SensorReading, SensorsResponse

router = APIRouter()

_TTL_SECONDS = 300
_cache: dict = {"ts": 0.0, "value": None}


def _fetch_combined() -> pd.DataFrame:
    purpleair_df = fetch_sensors()
    openaq_df = fetch_openaq()
    return pd.concat([purpleair_df, openaq_df], ignore_index=True)


def get_cached_sensors() -> pd.DataFrame:
    now = time.time()
    if _cache["value"] is not None and now - _cache["ts"] < _TTL_SECONDS:
        return _cache["value"]
    df = _fetch_combined()
    _cache["ts"] = now
    _cache["value"] = df
    return df


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


@router.get("/sensors", response_model=SensorsResponse, tags=["sensors"])
def get_sensors() -> SensorsResponse:
    """Live PM2.5 readings from PurpleAir + OpenAQ inside the Dallas bounding box.

    PurpleAir values are EPA-corrected at ingest. OpenAQ values are
    reference-grade and reported as-is. Cached for 5 minutes.
    """
    try:
        df = get_cached_sensors()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream sensor fetch failed: {e}")

    sensors = [_row_to_reading(row) for _, row in df.iterrows()]
    return SensorsResponse(
        count=len(sensors),
        timestamp=datetime.now(timezone.utc).isoformat(),
        sensors=sensors,
    )
