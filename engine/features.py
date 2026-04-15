# engine/features.py — Feature engineering: fuse sensor, traffic, and wind data
#
# Takes raw PurpleAir sensor readings and adjusts each sensor's PM2.5 value
# based on nearby traffic congestion and wind speed/direction.
# The output is the same DataFrame shape as the input — just with adjusted pm25 values —
# so the existing IDW interpolation in engine/interpolation.py works unchanged.

import numpy as np
import pandas as pd

from config import (
    LON_CORRECTION,          # cos(32.78°) ≈ 0.840 — corrects east-west degree distortion
    TRAFFIC_WEIGHT,          # max PM2.5 added by heavy traffic (µg/m³)
    TRAFFIC_DECAY_RADIUS_M,  # distance (m) at which traffic effect reaches zero
)

# Wind dispersal cap and curve parameters (unchanged from Phase 3)
WIND_WEIGHT    = 10.0   # strong wind can subtract up to 10 µg/m³ (dispersal effect)
WIND_SPEED_CAP = 15.0   # m/s — wind faster than this is treated as max dispersal

# Traffic exponential curve parameters (unchanged from Phase 3)
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


def _corrected_distance_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Approximate planar distance in degrees between two lat/lon points,
    with a cosine correction applied to the longitude delta so that
    east-west and north-south degrees are on an equal footing at Dallas's
    latitude (~32.78° N). Without the correction, 1° of longitude ≈ 0.84°
    of latitude in true distance, causing east-west distances to be
    overstated by ~19%.

    LON_CORRECTION = cos(radians(32.78)) ≈ 0.840
    """
    dlat = lat2 - lat1
    dlon = (lon2 - lon1) * LON_CORRECTION
    return float(np.sqrt(dlat ** 2 + dlon ** 2))


def _nearest_traffic_point(sensor_lat: float, sensor_lon: float, traffic_df: pd.DataFrame) -> tuple[pd.Series, float]:
    """
    Returns (nearest_row, corrected_distance_deg) for the traffic sample point
    closest to the sensor, using the cosine-corrected distance metric.
    """
    dlat = (traffic_df["lat"] - sensor_lat).values
    dlon = (traffic_df["lon"] - sensor_lon).values * LON_CORRECTION
    dists = np.sqrt(dlat ** 2 + dlon ** 2)
    idx = dists.argmin()
    return traffic_df.iloc[idx], float(dists[idx])


def _traffic_decay_multiplier(distance_deg: float) -> float:
    """
    Linear decay factor based on how far the sensor is from the nearest road.
    Converts the corrected degree distance to approximate meters (1° ≈ 111,000 m),
    then fades the traffic adjustment linearly from 1.0 at 0 m to 0.0 at
    TRAFFIC_DECAY_RADIUS_M (500 m). Sensors beyond that radius get zero effect.
    """
    distance_m = distance_deg * 111_000
    return float(max(0.0, 1.0 - (distance_m / TRAFFIC_DECAY_RADIUS_M)))


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

      +1.0 → wind blowing pollution AWAY from sensor (dispersal → subtract PM2.5)
      -1.0 → wind blowing pollution TOWARD sensor (transport → add PM2.5)
       0.0 → wind is perpendicular (no net effect)

    Sign convention (verified in __main__ test below):
      - bearing_rad = atan2(Δlon * LON_CORRECTION, Δlat) gives the compass bearing
        (measuring from north) from the traffic point TO the sensor, in radians.
      - wind_toward_rad is the direction the wind is blowing TOWARD.
        OWM reports where wind comes FROM, so we add 180° to get the toward direction.
      - alignment = cos(bearing_rad - wind_toward_rad)
          = +1 when wind-toward matches traffic→sensor bearing (wind carries pollution
            to sensor → bad, should ADD to pm25)
          = -1 when wind blows opposite (disperses away → should SUBTRACT from pm25)
      - We negate alignment so the returned factor is:
          -1 when wind transports pollution toward the sensor (pm25 increases)
          +1 when wind disperses pollution away (pm25 decreases)
      The caller does: pm25 -= direction_factor * dispersal * WIND_WEIGHT
      So factor=-1 → subtracting a negative → pm25 increases ✓
         factor=+1 → subtracting a positive → pm25 decreases ✓
    """
    traffic_lat = nearest["lat"]
    traffic_lon = nearest["lon"]

    delta_lat = sensor_lat - traffic_lat
    delta_lon = (sensor_lon - traffic_lon) * LON_CORRECTION  # apply cosine correction

    # If sensor and traffic point are essentially co-located, return neutral.
    if np.sqrt(delta_lat ** 2 + delta_lon ** 2) < 1e-6:
        return 0.0

    # Bearing (radians) from traffic point TO sensor, measured from north.
    bearing_rad = np.arctan2(delta_lon, delta_lat)

    # Direction wind is blowing TOWARD (OWM gives where it comes FROM).
    wind_toward_deg = (wind_deg + 180.0) % 360.0
    wind_toward_rad = np.deg2rad(wind_toward_deg)

    # +1 when wind-toward aligns with traffic→sensor bearing (wind carries pollution TO sensor).
    alignment = float(np.cos(bearing_rad - wind_toward_rad))

    # Negate: factor=-1 → caller subtracts negative → pm25 increases (pollution transported).
    #         factor=+1 → caller subtracts positive → pm25 decreases (pollution dispersed).
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
        # --- Traffic term ---
        if no_traffic:
            nearest      = None
            distance_deg = None
            congestion   = 0.0
        else:
            nearest, distance_deg = _nearest_traffic_point(row["lat"], row["lon"], traffic_df)
            congestion = float(nearest["congestion"])

        # Apply exponential congestion curve, then fade by distance to road.
        decay            = 0.0 if nearest is None else _traffic_decay_multiplier(distance_deg)
        traffic_adjustment = _traffic_factor(congestion) * decay * TRAFFIC_WEIGHT

        # --- Wind term ---
        if wind_speed == 0.0:
            # No wind — direction is meaningless; zero out the wind term entirely.
            direction_factor = 0.0
        elif wind_deg is None:
            # Wind speed exists but direction is missing — fall back to pure dispersal
            # (same as old behavior) rather than silently biasing toward north.
            direction_factor = 1.0
        elif nearest is None:
            # No traffic data — assume pure dispersal.
            direction_factor = 1.0
        else:
            direction_factor = _wind_direction_factor(row["lat"], row["lon"], nearest, wind_deg)

        wind_adjustment = direction_factor * dispersal * WIND_WEIGHT

        # pm25 += traffic (always positive), -= wind (positive = dispersal, negative = transport)
        adjusted = row["pm25"] + traffic_adjustment - wind_adjustment

        # Never let the adjustment push PM2.5 below zero
        df.at[idx, "pm25"] = max(0.0, adjusted)

    return df


# ---------------------------------------------------------------------------
# FIX 4 verification — wind direction sign logic
# ---------------------------------------------------------------------------
# Scenario: sensor at (32.80, -96.80), traffic point at (32.80, -96.81) (due west).
# Wind comes FROM the west (wind_deg = 270), meaning it blows TOWARD the east.
# The sensor is EAST of the traffic point, so wind is carrying traffic pollution
# straight toward the sensor → pm25 should INCREASE (wind_adjustment is negative).
if __name__ == "__main__":
    import pandas as pd

    sensor_lat, sensor_lon = 32.80, -96.80
    traffic_lat, traffic_lon = 32.80, -96.81
    wind_deg_test = 270.0   # wind coming FROM the west → blowing east

    nearest_test = pd.Series({"lat": traffic_lat, "lon": traffic_lon, "congestion": 0.8})

    delta_lat = sensor_lat - traffic_lat                          # 0.0
    delta_lon = (sensor_lon - traffic_lon) * LON_CORRECTION       # 0.01 * 0.840 ≈ +0.0084
    bearing_rad = np.arctan2(delta_lon, delta_lat)
    bearing_deg = np.degrees(bearing_rad)

    wind_toward_deg = (wind_deg_test + 180.0) % 360.0            # 90° → east
    wind_toward_rad = np.deg2rad(wind_toward_deg)

    angle_diff  = bearing_rad - wind_toward_rad
    alignment   = np.cos(angle_diff)
    direction_factor = -alignment

    wind_speed_test = 5.0
    dispersal_test  = _wind_dispersal_factor(wind_speed_test)
    wind_term       = direction_factor * dispersal_test * WIND_WEIGHT

    print("=== Wind direction sign verification ===")
    print(f"  bearing from traffic→sensor : {bearing_deg:.1f}°  (expect ≈90° east)")
    print(f"  wind_toward_deg             : {wind_toward_deg:.1f}°  (expect 90° east)")
    print(f"  angle_diff (rad)            : {angle_diff:.4f}  (expect ≈0)")
    print(f"  alignment (cos)             : {alignment:.4f}  (expect ≈+1)")
    print(f"  direction_factor            : {direction_factor:.4f}  (expect ≈-1)")
    print(f"  dispersal                   : {dispersal_test:.4f}")
    print(f"  wind_term (direction*disp*W): {wind_term:.4f}  (expect negative)")
    print(f"  pm25 change: raw - wind_term → raw - ({wind_term:.2f}) → raw + {-wind_term:.2f}")
    print("  ✓ CORRECT: pm25 INCREASES when wind blows pollution toward sensor" if wind_term < 0
          else "  ✗ BUG: wind_term is positive, pm25 would decrease — sign is wrong")
