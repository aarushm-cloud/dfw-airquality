# data/openaq.py — OpenAQ v3 sensor data ingestion

import logging
import os

import pandas as pd
import requests
from dotenv import load_dotenv

from config import BBOX, OPENAQ_API_KEY

load_dotenv()

logger = logging.getLogger(__name__)

OPENAQ_BASE_URL = "https://api.openaq.org/v3"
# parameters_id=2 is PM2.5 in OpenAQ's taxonomy
PM25_PARAMETER_ID = 2


def _get_api_key() -> str:
    key = os.getenv("OPENAQ_API_KEY", OPENAQ_API_KEY)
    if not key or key == "your_key_here":
        raise ValueError("OPENAQ_API_KEY is not set in your .env file.")
    return key


def _fetch_locations(api_key: str) -> list[dict]:
    """Return all PM2.5 locations within the Dallas bounding box."""
    params = {
        "bbox": f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}",
        "parameters_id": PM25_PARAMETER_ID,
        "limit": 100,
    }
    resp = requests.get(
        f"{OPENAQ_BASE_URL}/locations",
        params=params,
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _get_pm25_sensor_id(loc: dict) -> int | None:
    """Return the sensor ID for PM2.5 from a /locations result, or None."""
    for sensor in loc.get("sensors", []):
        if sensor.get("parameter", {}).get("id") == PM25_PARAMETER_ID:
            return sensor.get("id")
    return None


def _fetch_latest_pm25(location_id: int, pm25_sensor_id: int, api_key: str) -> float | None:
    """
    Fetch the latest PM2.5 value for a location from /locations/{id}/latest.
    The endpoint returns a flat list of readings keyed by sensorsId.
    """
    resp = requests.get(
        f"{OPENAQ_BASE_URL}/locations/{location_id}/latest",
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    for reading in resp.json().get("results", []):
        if reading.get("sensorsId") == pm25_sensor_id:
            value = reading.get("value")
            if value is not None:
                return float(value)
    return None


def fetch_openaq() -> pd.DataFrame:
    """
    Fetch live PM2.5 readings from OpenAQ v3 for the Dallas bounding box.

    Returns a DataFrame with columns:
        sensor_id, name, lat, lon, pm25, pm25_raw, epa_corrected, source

    OpenAQ readings come from reference-grade monitors and are NOT passed
    through the EPA PurpleAir correction. pm25_raw is NaN and epa_corrected
    is 0 so the frame lines up with the PurpleAir schema for concat.

    If OpenAQ is unreachable or returns no data, returns an empty DataFrame
    so the app can continue with PurpleAir data alone.
    """
    empty = pd.DataFrame(
        columns=["sensor_id", "name", "lat", "lon", "pm25", "pm25_raw", "epa_corrected", "source"]
    )

    try:
        api_key = _get_api_key()
    except ValueError as e:
        logger.warning("OpenAQ API key missing — skipping OpenAQ fetch. (%s)", e)
        return empty

    try:
        locations = _fetch_locations(api_key)
    except Exception as e:
        logger.warning("OpenAQ /locations request failed — skipping. (%s)", e)
        return empty

    if not locations:
        logger.warning("OpenAQ returned 0 locations for the Dallas bounding box.")
        return empty

    rows = []
    for loc in locations:
        loc_id = loc.get("id")
        name = loc.get("name", f"openaq-{loc_id}")
        coords = loc.get("coordinates", {})
        lat = coords.get("latitude")
        lon = coords.get("longitude")

        if lat is None or lon is None:
            continue

        pm25_sensor_id = _get_pm25_sensor_id(loc)
        if pm25_sensor_id is None:
            continue

        try:
            pm25 = _fetch_latest_pm25(loc_id, pm25_sensor_id, api_key)
        except Exception as e:
            logger.warning("OpenAQ latest fetch failed for location %s — skipping. (%s)", loc_id, e)
            continue

        if pm25 is None or pm25 < 0:
            continue

        rows.append({
            "sensor_id":     f"oaq-{loc_id}",
            "name":          name,
            "lat":           lat,
            "lon":           lon,
            "pm25":          pm25,
            # Reference-grade monitors — no uncorrected counterpart and no EPA
            # correction applied. Populate explicitly so the schema matches
            # PurpleAir when the two are concatenated downstream.
            "pm25_raw":      float("nan"),
            "epa_corrected": 0,
            "source":        "openaq",
        })

    if not rows:
        logger.warning("OpenAQ returned locations but no valid PM2.5 readings.")
        return empty

    return pd.DataFrame(
        rows,
        columns=["sensor_id", "name", "lat", "lon", "pm25", "pm25_raw", "epa_corrected", "source"],
    )
