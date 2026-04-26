# data/history.py — Accumulate live dashboard snapshots
#
# Each call to save_snapshot() appends one row per sensor to
# data/dashboard_snapshots.csv. These are live-pipeline snapshots taken while
# the Streamlit app or scripts/collector.py is running.
#
# Phase 4 training data is NOT collected here. The canonical training set is
# data/history.csv, built by data/collect_training_data.py from PurpleAir's
# historical API (see CLAUDE.md). Live snapshots and the training set live in
# separate files on purpose, so the training script can overwrite history.csv
# without corrupting the dashboard's accumulated state.

import os
import fcntl
import logging
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# CSV lives next to this file in the data/ directory.
# Training data (history.csv) is owned by data/collect_training_data.py;
# this writer owns dashboard_snapshots.csv so the two never collide.
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "dashboard_snapshots.csv")

COLUMNS = [
    "timestamp",
    "sensor_id",
    "lat",
    "lon",
    "pm25",             # EPA-corrected (PurpleAir) or reference-grade (OpenAQ) reading
    "pm25_raw",         # original uncorrected PurpleAir reading; NaN for OpenAQ
    "epa_corrected",    # 1 = EPA formula applied, 0 = raw fallback / OpenAQ
    "source",
    "wind_speed",
    "wind_deg",
    "nearest_congestion",     # raw congestion score (0–1) of nearest traffic point
    "distance_to_road_m",     # metres to nearest traffic sample point
    "traffic_factor",         # exponential congestion factor before TRAFFIC_WEIGHT scaling
    "wind_term",              # signed wind adjustment (µg/m³) for this sensor location
    "direction_factor",       # cosine wind direction alignment (-1 transport … +1 dispersal)
    "dispersal",              # wind speed dispersal strength (0–1)
    "hour_of_day",
    "day_of_week",
]


def save_snapshot(
    sensor_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
    wind: dict,
    timestamp: datetime | None = None,
) -> None:
    """
    Append one snapshot record per sensor to data/dashboard_snapshots.csv.

    sensor_df is the output of build_features(): pm25 is the EPA-corrected
    (PurpleAir) or reference-grade (OpenAQ) reading, pm25_raw holds the
    uncorrected PurpleAir value (NaN for OpenAQ), and the feature columns
    (traffic_factor, wind_term, direction_factor, etc.) are already computed
    and stored as separate columns. We read them directly from the row rather
    than recomputing them here.

    Args:
        sensor_df:  DataFrame from build_features() with pm25 (raw) and feature columns.
        traffic_df: DataFrame with [lat, lon, congestion] (kept for signature compat).
        wind:       Dict with wind_speed and wind_deg.
        timestamp:  Snapshot time (UTC). Defaults to datetime.now(timezone.utc).
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    ts_str      = timestamp.isoformat()
    hour_of_day = timestamp.hour
    day_of_week = timestamp.weekday()
    wind_speed  = float(wind.get("wind_speed") or 0.0)
    # Store NaN when wind_deg is missing rather than coercing to 0.0 (due North),
    # which would be a misleading value in the training dataset.
    raw_deg  = wind.get("wind_deg")
    wind_deg = float(raw_deg) if raw_deg is not None else float("nan")

    records = []
    for _, row in sensor_df.iterrows():
        records.append({
            "timestamp":          ts_str,
            "sensor_id":          row["sensor_id"],
            "lat":                row["lat"],
            "lon":                row["lon"],
            # pm25 is the EPA-corrected value (PurpleAir) or reference-grade
            # reading (OpenAQ); build_features() does not modify it further.
            "pm25":               row["pm25"],
            "pm25_raw":           row.get("pm25_raw", float("nan")),
            "epa_corrected":      row.get("epa_corrected", 0),
            "source":             row.get("source", "unknown"),
            "wind_speed":         wind_speed,
            "wind_deg":           wind_deg,
            # Feature columns computed by build_features() — read directly from row.
            "nearest_congestion": row.get("nearest_congestion", float("nan")),
            "distance_to_road_m": row.get("distance_to_road_m", float("nan")),
            "traffic_factor":     row.get("traffic_factor", float("nan")),
            "wind_term":          row.get("wind_term", float("nan")),
            "direction_factor":   row.get("direction_factor", float("nan")),
            "dispersal":          row.get("dispersal", float("nan")),
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
    Read data/dashboard_snapshots.csv and return it as a DataFrame.
    Returns an empty DataFrame with the correct columns if the file doesn't exist.
    """
    if not os.path.isfile(HISTORY_PATH):
        return pd.DataFrame(columns=COLUMNS)

    # on_bad_lines='skip' prevents a crash if the file has rows from an older
    # schema version with a different column count (e.g. after adding a new column).
    df = pd.read_csv(HISTORY_PATH, parse_dates=["timestamp"], on_bad_lines="skip")
    return df


def get_history_stats() -> dict:
    """
    Return a summary of the collected dashboard snapshots.

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
