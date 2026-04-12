# engine/features.py — Feature engineering: fuse sensor, traffic, and wind data
#
# Takes raw PurpleAir sensor readings and adjusts each sensor's PM2.5 value
# based on nearby traffic congestion and wind speed/direction.
# The output is the same DataFrame shape as the input — just with adjusted pm25 values —
# so the existing IDW interpolation in engine/interpolation.py works unchanged.

import numpy as np
import pandas as pd


# How much each factor can maximally shift PM2.5 (µg/m³)
TRAFFIC_WEIGHT    = 20.0  # heavy congestion can add up to 20 µg/m³
WIND_WEIGHT       = 10.0  # strong wind can subtract up to 10 µg/m³ (dispersal effect)
WIND_SPEED_CAP    = 15.0  # m/s — wind faster than this is treated as max dispersal

# Traffic exponential curve parameters
TRAFFIC_THRESHOLD = 0.3   # congestion below this is treated as negligible
TRAFFIC_CURVE_K   = 3.0   # steepness of exponential growth above threshold


def _traffic_factor(congestion: float) -> float:
    """
    Converts a raw congestion score (0–1) to a PM2.5 adjustment factor (0–1).
    Below TRAFFIC_THRESHOLD: returns 0 (light traffic has negligible impact).
    Above threshold: rescales to [0,1] then applies exponential growth,
    so the effect only becomes significant near heavy congestion.
    """
    if congestion < TRAFFIC_THRESHOLD:
        return 0.0
    scaled = (congestion - TRAFFIC_THRESHOLD) / (1.0 - TRAFFIC_THRESHOLD)
    k = TRAFFIC_CURVE_K
    return (np.exp(k * scaled) - 1.0) / (np.exp(k) - 1.0)


def _nearest_traffic_point(sensor_lat: float, sensor_lon: float, traffic_df: pd.DataFrame) -> pd.Series:
    """Returns the row of the closest traffic sample point to a sensor."""
    dists = np.sqrt(
        (traffic_df["lat"] - sensor_lat) ** 2 +
        (traffic_df["lon"] - sensor_lon) ** 2
    )
    return traffic_df.loc[dists.idxmin()]


def _congestion_from_point(nearest: pd.Series) -> float:
    """Extract the congestion score from a pre-fetched nearest traffic point."""
    return float(nearest["congestion"])


def _wind_dispersal_factor(wind_speed: float) -> float:
    """
    Returns a 0–1 value representing wind speed's dispersal strength.
    0 = calm (no dispersal), 1 = strong wind (maximum dispersal).
    """
    return float(np.clip(wind_speed / WIND_SPEED_CAP, 0.0, 1.0))


def _wind_direction_factor(
    sensor_lat: float,
    sensor_lon: float,
    nearest: pd.Series,
    wind_deg: float,
) -> float:
    """
    Returns a multiplier from -1.0 to +1.0 based on whether wind is carrying
    pollution from the nearest traffic source toward this sensor, or away from it.

      +1.0 → wind blowing pollution AWAY from sensor (dispersal, subtract PM2.5)
      -1.0 → wind blowing pollution TOWARD sensor (transport, add PM2.5)
       0.0 → wind is perpendicular (no net effect)

    Accepts a pre-fetched nearest traffic point Series to avoid recomputing
    distances when the caller already has it.

    Approach:
      1. Compute the bearing from the nearest traffic point TO the sensor.
         This is the direction pollution would travel to reach the sensor.
      2. Compute the direction wind is blowing TOWARD (wind_deg is the direction
         it comes FROM, so we add 180° to get the toward direction).
      3. Use cosine of the angle between them as a smooth similarity measure.
         cos=+1 means wind is blowing from traffic toward sensor (bad).
         We negate it so the result is -1 when wind transports pollution toward
         the sensor, and +1 when wind blows pollution away.
    """
    traffic_lat = nearest["lat"]
    traffic_lon = nearest["lon"]

    # Bearing from traffic point to sensor (0=N, 90=E, 180=S, 270=W).
    # atan2(Δlon, Δlat) matches meteorological bearing convention at city scale
    # where we can treat the Earth as flat (same assumption as IDW interpolation).
    delta_lat = sensor_lat - traffic_lat
    delta_lon = sensor_lon - traffic_lon

    # If the sensor and traffic point are essentially co-located, atan2(0, 0)
    # would return 0 (arbitrary north bearing). Return neutral instead.
    if np.sqrt(delta_lat ** 2 + delta_lon ** 2) < 1e-6:
        return 0.0

    bearing_rad = np.arctan2(delta_lon, delta_lat)  # angle from north, in radians

    # Direction wind is blowing TOWARD (OWM gives direction it comes FROM)
    wind_toward_deg = (wind_deg + 180.0) % 360.0
    wind_toward_rad = np.deg2rad(wind_toward_deg)

    # Cosine of the angle between the two bearings.
    # +1 means wind toward sensor matches bearing from traffic to sensor
    # (wind is carrying traffic pollution straight at the sensor).
    angle_diff = bearing_rad - wind_toward_rad
    alignment = float(np.cos(angle_diff))

    # Negate: alignment=+1 (wind toward sensor) → factor=-1 (adds pollution)
    #         alignment=-1 (wind away from sensor) → factor=+1 (dispersal)
    return -alignment


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

    wind_speed = wind.get("wind_speed") or 0.0
    wind_deg   = wind.get("wind_deg")  # may be None if OWM didn't return it

    dispersal  = _wind_dispersal_factor(wind_speed)

    no_traffic = traffic_df is None or traffic_df.empty

    for idx, row in df.iterrows():
        # Compute the nearest traffic point once and reuse it for both
        # the congestion lookup and the wind direction calculation.
        nearest = None if no_traffic else _nearest_traffic_point(row["lat"], row["lon"], traffic_df)

        congestion = 0.0 if nearest is None else _congestion_from_point(nearest)

        # direction_factor: +1 = wind dispersing away, -1 = wind carrying toward sensor
        if wind_speed == 0.0:
            # No wind — direction is meaningless, zero out the wind term entirely
            direction_factor = 0.0
        elif wind_deg is None:
            # Wind speed exists but direction is missing — fall back to pure dispersal
            # (same as old behavior) rather than silently biasing toward north
            direction_factor = 1.0
        elif nearest is None:
            # No traffic data — assume pure dispersal
            direction_factor = 1.0
        else:
            direction_factor = _wind_direction_factor(row["lat"], row["lon"], nearest, wind_deg)

        traffic_adjustment = _traffic_factor(congestion) * TRAFFIC_WEIGHT
        wind_adjustment    = direction_factor * dispersal * WIND_WEIGHT

        adjusted = row["pm25"] + traffic_adjustment - wind_adjustment

        # Never let the adjustment push PM2.5 below zero
        df.at[idx, "pm25"] = max(0.0, adjusted)

    return df
