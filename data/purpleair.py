# data/purpleair.py — PurpleAir sensor data ingestion

import os
import requests
import pandas as pd
from dotenv import load_dotenv
from config import BBOX, PURPLEAIR_BASE_URL

load_dotenv()


def get_api_key() -> str:
    """Load PurpleAir API key from .env."""
    key = os.getenv("PURPLEAIR_API_KEY")
    if not key or key == "your_key_here":
        raise ValueError("PURPLEAIR_API_KEY is not set in your .env file.")
    return key


def fetch_sensors() -> pd.DataFrame:
    """
    Fetch all outdoor PurpleAir sensors within the Dallas bounding box.

    Returns a DataFrame with columns:
        sensor_id, name, lat, lon, pm25

    pm25 is the 10-minute average PM2.5 (µg/m³) from channel A.
    Only outdoor sensors (location_type == 0) are included.
    """
    api_key = get_api_key()

    # Fields we want back from the API
    fields = [
        "sensor_index",
        "name",
        "latitude",
        "longitude",
        "pm2.5_10minute",
        "location_type",
    ]

    params = {
        "fields":     ",".join(fields),
        "location_type": 0,          # 0 = outdoor only
        "nwlng":      BBOX["west"],
        "nwlat":      BBOX["north"],
        "selng":      BBOX["east"],
        "selat":      BBOX["south"],
    }

    headers = {"X-API-Key": api_key}

    response = requests.get(
        f"{PURPLEAIR_BASE_URL}/sensors",
        params=params,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()

    # The API returns {"fields": [...], "data": [[...], ...]}
    field_names = data.get("fields", [])
    rows = data.get("data", [])

    if not rows:
        # Return an empty DataFrame with the right columns
        return pd.DataFrame(columns=["sensor_id", "name", "lat", "lon", "pm25", "source"])

    df = pd.DataFrame(rows, columns=field_names)

    # Rename to friendlier column names
    df = df.rename(columns={
        "sensor_index":     "sensor_id",
        "latitude":         "lat",
        "longitude":        "lon",
        "pm2.5_10minute":   "pm25",
    })

    # Drop rows where PM2.5 reading is missing or negative.
    # Zero is a valid reading (very clean air). PurpleAir returns null for offline sensors,
    # not zero — so null is what we drop here. Negative values indicate sensor malfunction.
    df = df.dropna(subset=["pm25"])
    df = df[df["pm25"] >= 0]

    # Keep only the columns we need and tag the source
    df = df[["sensor_id", "name", "lat", "lon", "pm25"]].copy()
    df["source"] = "purpleair"

    return df


def classify_pm25(pm25: float) -> str:
    """
    Classify a PM2.5 value (µg/m³) into an AQI category string.
    Mirrors the thresholds in config.py.
    """
    if pm25 <= 12.0:
        return "good"
    elif pm25 <= 35.4:
        return "moderate"
    elif pm25 <= 55.4:
        return "sensitive"
    elif pm25 <= 150.4:
        return "unhealthy"
    elif pm25 <= 250.4:
        return "very_unhealthy"
    else:
        return "hazardous"
