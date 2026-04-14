# data/history.py — Accumulate air quality snapshots for ML training (Phase 4)
#
# Each call to save_snapshot() appends one row per sensor to data/history.csv.
# Over time this builds a labeled dataset for training a Random Forest model
# that can replace IDW interpolation.

import os
import fcntl
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# CSV lives next to this file in the data/ directory
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "history.csv")

COLUMNS = [
    "timestamp",
    "sensor_id",
    "lat",
    "lon",
    "pm25",
    "pm25_raw",
    "source",
    "wind_speed",
    "wind_deg",
    "nearest_congestion",
    "hour_of_day",
    "day_of_week",
]


def _nearest_congestion(sensor_lat: float, sensor_lon: float, traffic_df: pd.DataFrame) -> float:
    """Return the congestion score of the closest traffic point to a sensor."""
    dists = np.sqrt(
        (traffic_df["lat"] - sensor_lat) ** 2 +
        (traffic_df["lon"] - sensor_lon) ** 2
    )
    return float(traffic_df.loc[dists.idxmin(), "congestion"])


def save_snapshot(
    sensor_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
    wind: dict,
    timestamp: datetime | None = None,
) -> None:
    """
    Append one training record per sensor to data/history.csv.

    Args:
        sensor_df:  DataFrame after build_features() — pm25 is adjusted,
                    pm25_raw (if present) is the original reading.
        traffic_df: DataFrame with [lat, lon, congestion].
        wind:       Dict with wind_speed and wind_deg.
        timestamp:  Snapshot time (UTC). Defaults to datetime.utcnow().
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    ts_str       = timestamp.isoformat()
    hour_of_day  = timestamp.hour
    day_of_week  = timestamp.weekday()
    wind_speed   = float(wind.get("wind_speed") or 0.0)
    wind_deg     = float(wind.get("wind_deg") or 0.0)
    no_traffic   = traffic_df is None or traffic_df.empty

    records = []
    for _, row in sensor_df.iterrows():
        congestion = (
            0.0 if no_traffic
            else _nearest_congestion(row["lat"], row["lon"], traffic_df)
        )

        records.append({
            "timestamp":          ts_str,
            "sensor_id":          row["sensor_id"],
            "lat":                row["lat"],
            "lon":                row["lon"],
            "pm25":               row["pm25"],
            "pm25_raw":           row.get("pm25_raw", row["pm25"]),
            "source":             row.get("source", "unknown"),
            "wind_speed":         wind_speed,
            "wind_deg":           wind_deg,
            "nearest_congestion": congestion,
            "hour_of_day":        hour_of_day,
            "day_of_week":        day_of_week,
        })

    new_rows = pd.DataFrame(records, columns=COLUMNS)

    file_exists = os.path.isfile(HISTORY_PATH)

    # Open in append mode and hold an exclusive lock for the duration of the write
    # to prevent corruption if two Streamlit sessions run simultaneously.
    with open(HISTORY_PATH, "a", newline="") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            new_rows.to_csv(f, index=False, header=not file_exists)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load_history() -> pd.DataFrame:
    """
    Read data/history.csv and return it as a DataFrame.
    Returns an empty DataFrame with the correct columns if the file doesn't exist.
    """
    if not os.path.isfile(HISTORY_PATH):
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(HISTORY_PATH, parse_dates=["timestamp"])
    return df


def get_history_stats() -> dict:
    """
    Return a summary of the collected training data.

    Returns:
        total_records:  total row count
        unique_sensors: number of distinct sensor IDs seen
        date_range:     (earliest, latest) timestamp as ISO strings, or (None, None)
        hours_covered:  number of distinct hours in the dataset
    """
    df = load_history()

    if df.empty:
        return {
            "total_records":  0,
            "unique_sensors": 0,
            "date_range":     (None, None),
            "hours_covered":  0,
        }

    return {
        "total_records":  len(df),
        "unique_sensors": df["sensor_id"].nunique(),
        "date_range":     (
            str(df["timestamp"].min()),
            str(df["timestamp"].max()),
        ),
        "hours_covered":  df["timestamp"].dt.floor("h").nunique(),
    }
