# engine/features.py — Feature engineering: fuse sensor, traffic, and wind data
#
# Takes raw PurpleAir sensor readings and adjusts each sensor's PM2.5 value
# based on nearby traffic congestion and wind speed/direction.
# The output is the same DataFrame shape as the input — just with adjusted pm25 values —
# so the existing IDW interpolation in engine/interpolation.py works unchanged.

import numpy as np
import pandas as pd


# How much each factor can maximally shift PM2.5 (µg/m³)
TRAFFIC_WEIGHT = 20.0   # heavy congestion can add up to 20 µg/m³
WIND_WEIGHT    = 10.0   # strong wind can subtract up to 10 µg/m³ (dispersal effect)
WIND_SPEED_CAP = 15.0   # m/s — wind faster than this is treated as max dispersal


def _nearest_congestion(sensor_lat: float, sensor_lon: float, traffic_df: pd.DataFrame) -> float:
    """Find the congestion score of the closest traffic sample point to a sensor."""
    if traffic_df.empty:
        return 0.0

    dists = np.sqrt(
        (traffic_df["lat"] - sensor_lat) ** 2 +
        (traffic_df["lon"] - sensor_lon) ** 2
    )
    return float(traffic_df.loc[dists.idxmin(), "congestion"])


def _wind_dispersal_factor(wind_speed: float) -> float:
    """
    Returns a 0–1 value representing how much wind is dispersing pollution.
    0 = calm (no dispersal), 1 = strong wind (maximum dispersal).
    """
    return float(np.clip(wind_speed / WIND_SPEED_CAP, 0.0, 1.0))


def build_features(
    sensor_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
    wind: dict,
) -> pd.DataFrame:
    """
    Adjusts each sensor's PM2.5 reading using traffic and wind context.

    Args:
        sensor_df:  DataFrame with [sensor_id, name, lat, lon, pm25]
        traffic_df: DataFrame with [lat, lon, congestion] from fetch_traffic()
        wind:       Dict with wind_speed and wind_deg from fetch_wind()

    Returns:
        Copy of sensor_df with pm25 values adjusted and a new column pm25_raw
        preserving the original reading.
    """
    df = sensor_df.copy()

    # Keep the original reading for reference
    df["pm25_raw"] = df["pm25"]

    dispersal = _wind_dispersal_factor(wind.get("wind_speed", 0.0))

    for idx, row in df.iterrows():
        congestion = _nearest_congestion(row["lat"], row["lon"], traffic_df)

        # Traffic adds pollution; wind disperses it
        traffic_adjustment = congestion * TRAFFIC_WEIGHT
        wind_adjustment    = dispersal  * WIND_WEIGHT

        adjusted = row["pm25"] + traffic_adjustment - wind_adjustment

        # Never let the adjustment push PM2.5 below zero
        df.at[idx, "pm25"] = max(0.0, adjusted)

    return df
