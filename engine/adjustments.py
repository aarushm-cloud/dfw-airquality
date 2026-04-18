# engine/adjustments.py — Shared traffic and wind adjustment helpers
#
# Used by both engine/features.py (to compute per-sensor feature columns for
# ML training data) and engine/interpolation.py (to adjust interpolated grid
# cells post-IDW). Centralised here to avoid code duplication.

import numpy as np
import pandas as pd

from config import (
    LON_CORRECTION,          # cos(32.78°) ≈ 0.840 — corrects east-west degree distortion
    TRAFFIC_WEIGHT,          # max PM2.5 added by heavy traffic (µg/m³)
    TRAFFIC_DECAY_RADIUS_M,  # distance (m) at which traffic effect reaches zero
)

# Wind dispersal cap and curve parameters
WIND_WEIGHT    = 10.0   # strong wind can subtract up to 10 µg/m³ (dispersal effect)
WIND_SPEED_CAP = 15.0   # m/s — wind faster than this is treated as max dispersal

# Traffic exponential curve parameters
TRAFFIC_THRESHOLD = 0.3   # congestion below this is treated as negligible
TRAFFIC_CURVE_K   = 3.0   # steepness of exponential growth above threshold


# ---------------------------------------------------------------------------
# Per-point scalar helpers (used by features.py row-by-row)
# ---------------------------------------------------------------------------

def traffic_factor(congestion: float) -> float:
    """
    Converts a raw congestion score (0–1) to a PM2.5 adjustment factor (0–1).
    Below TRAFFIC_THRESHOLD: returns 0 (light traffic has negligible impact).
    Above threshold: rescales to [0,1] then applies exponential growth.
    """
    if congestion < TRAFFIC_THRESHOLD:
        return 0.0
    scaled = (congestion - TRAFFIC_THRESHOLD) / (1.0 - TRAFFIC_THRESHOLD)
    k = TRAFFIC_CURVE_K
    return (np.exp(k * scaled) - 1.0) / (np.exp(k) - 1.0)


def nearest_traffic_point(lat: float, lon: float, traffic_df: pd.DataFrame) -> tuple[pd.Series, float]:
    """
    Returns (nearest_row, corrected_distance_deg) for the traffic sample
    point closest to the given lat/lon, using the cosine-corrected metric.
    """
    dlat = (traffic_df["lat"] - lat).values
    dlon = (traffic_df["lon"] - lon).values * LON_CORRECTION
    dists = np.sqrt(dlat ** 2 + dlon ** 2)
    idx = dists.argmin()
    return traffic_df.iloc[idx], float(dists[idx])


def traffic_decay_multiplier(distance_deg: float) -> float:
    """
    Linear decay factor: 1.0 at 0 m, 0.0 at TRAFFIC_DECAY_RADIUS_M (500 m).
    Sensors / grid cells beyond that radius get zero traffic effect.
    Converts corrected degree distance to metres (1° ≈ 111,000 m).
    """
    distance_m = distance_deg * 111_000
    return float(max(0.0, 1.0 - (distance_m / TRAFFIC_DECAY_RADIUS_M)))


def wind_dispersal_factor(wind_speed: float) -> float:
    """
    Returns a 0–1 value representing wind speed's dispersal strength.
    0 = calm (no dispersal), 1 = strong wind (maximum dispersal).

    Uses a square-root curve because atmospheric dispersion research shows
    PM2.5 concentration drops sharply in the first few m/s of wind — light
    to moderate wind does most of the dispersal work, while additional wind
    speed has diminishing returns.
    """
    return float(np.clip((wind_speed / WIND_SPEED_CAP) ** 0.5, 0.0, 1.0))


def wind_direction_factor(
    point_lat: float,
    point_lon: float,
    nearest: pd.Series,
    wind_deg: float,
) -> float:
    """
    Returns a multiplier from -1.0 to +1.0 based on whether wind is carrying
    pollution from the nearest traffic source toward this point, or away from it.

      +1.0 → wind blowing pollution AWAY (dispersal → subtract PM2.5)
      -1.0 → wind blowing pollution TOWARD (transport → add PM2.5)
       0.0 → wind is perpendicular (no net effect)

    The caller applies: pm25 -= direction_factor * dispersal * WIND_WEIGHT
      factor = -1 → subtracting a negative → pm25 increases (transport) ✓
      factor = +1 → subtracting a positive → pm25 decreases (dispersal) ✓
    """
    traffic_lat = nearest["lat"]
    traffic_lon = nearest["lon"]

    delta_lat = point_lat - traffic_lat
    delta_lon = (point_lon - traffic_lon) * LON_CORRECTION

    # If point and traffic source are essentially co-located, return neutral.
    if np.sqrt(delta_lat ** 2 + delta_lon ** 2) < 1e-6:
        return 0.0

    # Bearing (radians) from traffic point TO the target point, measured from north.
    bearing_rad = np.arctan2(delta_lon, delta_lat)

    # OWM reports where wind comes FROM — add 180° to get toward direction.
    wind_toward_rad = np.deg2rad((wind_deg + 180.0) % 360.0)

    # +1 when wind-toward aligns with traffic→point bearing (wind carries pollution here).
    alignment = float(np.cos(bearing_rad - wind_toward_rad))

    # Negate so the returned value is +1 for dispersal, -1 for transport.
    return -alignment


# ---------------------------------------------------------------------------
# Vectorised helpers (used by interpolation.py for the full grid at once)
# ---------------------------------------------------------------------------

def traffic_factor_vec(congestion: np.ndarray) -> np.ndarray:
    """
    Vectorised version of traffic_factor().
    Input:  congestion array of shape (N,)
    Output: factor array of shape (N,), values in [0, 1]
    """
    below = congestion < TRAFFIC_THRESHOLD
    scaled = np.clip(
        (congestion - TRAFFIC_THRESHOLD) / (1.0 - TRAFFIC_THRESHOLD),
        0.0, None,
    )
    k = TRAFFIC_CURVE_K
    factor = (np.exp(k * scaled) - 1.0) / (np.exp(k) - 1.0)
    return np.where(below, 0.0, factor)


def wind_direction_factor_vec(
    cell_lats: np.ndarray,
    cell_lons: np.ndarray,
    t_lats: np.ndarray,
    t_lons: np.ndarray,
    nearest_idx: np.ndarray,
    wind_deg: float,
) -> np.ndarray:
    """
    Vectorised wind direction factor for all grid cells at once.

    Args:
        cell_lats / cell_lons : (N,) flattened grid coordinates
        t_lats / t_lons       : (T,) traffic point coordinates
        nearest_idx           : (N,) index of the nearest traffic point per cell
        wind_deg              : wind origin direction in degrees (OWM convention)

    Returns:
        direction_factor array of shape (N,), values in [-1, 1]
    """
    nearest_t_lats = t_lats[nearest_idx]
    nearest_t_lons = t_lons[nearest_idx]

    delta_lat = cell_lats - nearest_t_lats
    delta_lon = (cell_lons - nearest_t_lons) * LON_CORRECTION

    dist = np.sqrt(delta_lat ** 2 + delta_lon ** 2)

    bearing_rad     = np.arctan2(delta_lon, delta_lat)
    wind_toward_rad = np.deg2rad((wind_deg + 180.0) % 360.0)

    alignment = np.cos(bearing_rad - wind_toward_rad)

    # Negate: +1 = dispersal, -1 = transport (same sign convention as scalar version)
    direction_factor = -alignment

    # Zero out cells that are co-located with their nearest traffic point
    return np.where(dist < 1e-6, 0.0, direction_factor)
