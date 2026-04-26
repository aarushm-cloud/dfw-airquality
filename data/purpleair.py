# data/purpleair.py — PurpleAir sensor data ingestion
#
# Every PurpleAir reading returned by this module has been EPA-corrected at
# the source: pm25 is the corrected value, pm25_raw is the original laser-
# counter reading, and epa_corrected flags which rows had humidity available.
# Downstream code should treat pm25 as already corrected and NOT apply the
# formula again.

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


def apply_epa_correction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the EPA's PM2.5 correction formula for PurpleAir sensors:

        PM2.5_corrected = 0.52 * PM2.5_raw - 0.085 * RH + 5.71

    TODO: this is duplicated in data/collect_training_data.py:apply_epa_correction
    (the training script can't import from this module without booting up the
    live PurpleAir endpoint). Both must be edited in lockstep. Follow-up:
    extract into a shared data/corrections.py module.

    PurpleAir's laser particle counter systematically overestimates PM2.5,
    especially at higher humidity, because water droplets scatter laser light
    and get counted as particles. The EPA's regression formula, derived from
    years of co-location studies with federal reference-grade monitors, is the
    standard correction in U.S. regulatory and public health contexts (see
    EPA's AirNow Fire and Smoke Map technical documentation).

    Behaviour:
      - Rows with humidity present are corrected.
      - Rows with missing humidity fall back to the raw reading.
      - epa_corrected flags which rows were corrected (1) vs. left raw (0).
      - Corrected values are clipped to >= 0 (the formula can produce small
        negatives at very low concentrations).
      - The original reading is preserved in pm25_raw for audit purposes.
    """
    out = df.copy()
    out["pm25_raw"] = out["pm25"]

    # If humidity wasn't returned at all, every row stays uncorrected.
    if "humidity" not in out.columns:
        out["epa_corrected"] = 0
        return out

    has_rh = out["humidity"].notna()

    corrected = 0.52 * out["pm25_raw"] - 0.085 * out["humidity"] + 5.71
    out.loc[has_rh, "pm25"] = corrected[has_rh].clip(lower=0)

    out["epa_corrected"] = has_rh.astype(int)
    return out


def fetch_sensors() -> pd.DataFrame:
    """
    Fetch all outdoor PurpleAir sensors within the Dallas bounding box.

    Returns a DataFrame with columns:
        sensor_id, name, lat, lon, pm25, pm25_raw, epa_corrected, source

    pm25 is the EPA-corrected 10-minute average PM2.5 (µg/m³).
    pm25_raw is the original uncorrected reading.
    epa_corrected is 1 if the formula was applied, 0 if humidity was missing.
    Only outdoor sensors (location_type == 0) are included.
    """
    api_key = get_api_key()

    # Fields we want back from the API. humidity is required for the EPA
    # correction formula applied below.
    fields = [
        "sensor_index",
        "name",
        "latitude",
        "longitude",
        "pm2.5_10minute",
        "humidity",
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

    empty_cols = ["sensor_id", "name", "lat", "lon", "pm25", "pm25_raw", "epa_corrected", "source"]
    if not rows:
        return pd.DataFrame(columns=empty_cols)

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

    # Apply the EPA correction AFTER NaN/negative filtering so the formula only
    # sees real readings. pm25 becomes the corrected value; pm25_raw preserves
    # the original for audit.
    df = apply_epa_correction(df)

    # Keep only the columns we need and tag the source
    df = df[["sensor_id", "name", "lat", "lon", "pm25", "pm25_raw", "epa_corrected"]].copy()
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
