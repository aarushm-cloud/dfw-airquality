# engine/interpolation.py — IDW (Inverse Distance Weighting) interpolation
#
# For each point on a grid, computes a weighted average of all sensor PM2.5 values.
# Sensors closer to a grid point get more weight: weight = 1 / distance^IDW_POWER
# A search radius (IDW_SEARCH_RADIUS_DEG) limits which sensors contribute to each
# cell — distant sensors get zero weight rather than a tiny but nonzero pull.
# Result: a smooth PM2.5 surface over Dallas we can render as a heatmap.
#
# adjust_grid() is called AFTER run_idw() to apply traffic and wind corrections to
# each interpolated cell. Because IDW knows nothing about roads or wind, these
# adjustments belong here — not on the raw sensor readings (which already reflect
# real-world traffic and wind conditions at the sensor locations).

import numpy as np
import pandas as pd

from config import BBOX, LON_CORRECTION, IDW_POWER, IDW_SEARCH_RADIUS_DEG, TRAFFIC_WEIGHT, TRAFFIC_DECAY_RADIUS_M
from engine.adjustments import (
    WIND_WEIGHT,
    WIND_SPEED_CAP,
    TRAFFIC_THRESHOLD,
    TRAFFIC_CURVE_K,
    wind_dispersal_factor,
    traffic_factor_vec,
    wind_direction_factor_vec,
)


def run_idw(
    df: pd.DataFrame,
    grid_resolution: int = 100,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns three 2D arrays of the same shape: (lats_2d, lons_2d, interpolated_pm25).
    grid_resolution controls grid density (100 = 100x100 points over Dallas).

    Changes vs Phase 3:
      - power is now IDW_POWER (3) from config, not hardcoded 2
      - longitude deltas are multiplied by LON_CORRECTION (cos 32.78°) before
        squaring so east-west distances aren't overstated by ~19%
      - sensors beyond IDW_SEARCH_RADIUS_DEG get zero weight for each cell;
        if no sensors are within radius for a cell, fall back to the
        unweighted mean of all sensors (avoids NaN in sparse areas)
    """
    # Build a regular lat/lon grid over the Dallas bounding box
    lat_grid = np.linspace(BBOX["south"], BBOX["north"], grid_resolution)
    lon_grid = np.linspace(BBOX["west"],  BBOX["east"],  grid_resolution)
    lons_2d, lats_2d = np.meshgrid(lon_grid, lat_grid)

    sensor_lats = df["lat"].values.astype(np.float64)
    sensor_lons = df["lon"].values.astype(np.float64)
    sensor_pm25 = df["pm25"].values.astype(np.float64)

    # Reshape for numpy broadcasting: grid points (res, res, 1) vs sensors (1, 1, n)
    lats_3d = lats_2d[:, :, np.newaxis]
    lons_3d = lons_2d[:, :, np.newaxis]
    s_lats  = sensor_lats[np.newaxis, np.newaxis, :]
    s_lons  = sensor_lons[np.newaxis, np.newaxis, :]

    # Cosine-corrected planar distance in degrees.
    # Multiply longitude differences by LON_CORRECTION so that 1° lon ≈ 1° lat
    # in true distance at Dallas's latitude, avoiding ~19% east-west overstatement.
    dlat      = lats_3d - s_lats
    dlon      = (lons_3d - s_lons) * LON_CORRECTION
    distances = np.sqrt(dlat ** 2 + dlon ** 2)

    # Avoid divide-by-zero when a grid point sits exactly on a sensor location
    distances = np.where(distances == 0, 1e-10, distances)

    # Zero out weight for sensors beyond the search radius.
    # This prevents a distant sensor from having a small but nonzero pull on
    # every cell across the map, which smears local variation.
    in_radius = distances <= IDW_SEARCH_RADIUS_DEG   # shape: (res, res, n_sensors)

    weights = 1.0 / (distances ** IDW_POWER)
    weights = np.where(in_radius, weights, 0.0)      # mask out-of-radius sensors

    weight_total = np.sum(weights, axis=2)            # shape: (res, res)

    # Where at least one sensor is within radius, use the normal IDW estimate.
    # Where no sensor is within radius (sparse edges), fall back to the global
    # unweighted mean so those cells still get a reasonable value (not NaN).
    global_mean    = float(np.mean(sensor_pm25))
    has_neighbours = weight_total > 0                 # shape: (res, res)

    weighted_sum  = np.sum(weights * sensor_pm25[np.newaxis, np.newaxis, :], axis=2)
    idw_estimate  = np.where(has_neighbours, weighted_sum / np.where(has_neighbours, weight_total, 1.0), global_mean)

    return lats_2d, lons_2d, idw_estimate


def adjust_grid(
    grid_values: np.ndarray,
    lats_2d: np.ndarray,
    lons_2d: np.ndarray,
    traffic_df: pd.DataFrame,
    wind: dict,
) -> np.ndarray:
    """
    Apply traffic and wind adjustments to an interpolated grid post-IDW.

    IDW alone produces a smooth PM2.5 surface based only on sensor proximity.
    This step adds the road-level and wind context that IDW cannot infer:
      - Grid cells near congested roads get a positive PM2.5 boost.
      - Grid cells downwind of traffic sources get an additional boost;
        cells upwind get a dispersal reduction.

    The same exponential traffic curve and cosine wind direction logic used
    in features.py is applied here, but fully vectorised with NumPy so that
    the entire 100×100 grid is processed in one set of array operations
    (milliseconds, not seconds).

    Args:
        grid_values : (res, res) array of IDW-interpolated PM2.5 values
        lats_2d     : (res, res) array of grid point latitudes
        lons_2d     : (res, res) array of grid point longitudes
        traffic_df  : DataFrame with [lat, lon, congestion], or None / empty
        wind        : dict with wind_speed (m/s) and wind_deg (degrees from OWM)

    Returns:
        Adjusted grid_values array of the same shape, clamped to >= 0.0.
    """
    # If no traffic data, return the IDW grid unchanged.
    if traffic_df is None or traffic_df.empty:
        return grid_values

    wind_speed = float(wind.get("wind_speed") or 0.0)
    wind_deg   = wind.get("wind_deg")

    # Flatten the 2D grid to 1D for vectorised operations, then reshape at the end.
    cell_lats = lats_2d.ravel()   # (N,)
    cell_lons = lons_2d.ravel()   # (N,)
    flat_vals = grid_values.ravel().copy()   # (N,)
    N = len(cell_lats)

    t_lats = traffic_df["lat"].values.astype(np.float64)    # (T,)
    t_lons = traffic_df["lon"].values.astype(np.float64)    # (T,)
    t_cong = traffic_df["congestion"].values.astype(np.float64)  # (T,)
    T = len(t_lats)

    # --- Distance from every grid cell to every traffic point ---
    # Shape: (N, T).  Use broadcasting: cells as column vectors, traffic as row vectors.
    dlat = cell_lats[:, np.newaxis] - t_lats[np.newaxis, :]   # (N, T)
    dlon = (cell_lons[:, np.newaxis] - t_lons[np.newaxis, :]) * LON_CORRECTION  # (N, T)
    dists_deg = np.sqrt(dlat ** 2 + dlon ** 2)                # (N, T)

    # Index of the nearest traffic point for each grid cell
    nearest_idx = dists_deg.argmin(axis=1)                    # (N,)
    nearest_dist_deg = dists_deg[np.arange(N), nearest_idx]   # (N,)
    nearest_cong = t_cong[nearest_idx]                        # (N,)

    # --- Traffic adjustment ---
    # Exponential congestion curve (vectorised)
    tf = traffic_factor_vec(nearest_cong)                     # (N,), in [0, 1]

    # Linear distance decay: full effect at 0 m, zero at TRAFFIC_DECAY_RADIUS_M
    dist_m = nearest_dist_deg * 111_000                       # (N,) in metres
    decay  = np.clip(1.0 - dist_m / TRAFFIC_DECAY_RADIUS_M, 0.0, 1.0)  # (N,)

    traffic_adj = tf * decay * TRAFFIC_WEIGHT                 # (N,) µg/m³

    # --- Wind adjustment ---
    if wind_speed == 0.0 or wind_deg is None:
        # No wind or unknown direction — apply no wind correction.
        wind_adj = np.zeros(N)
    else:
        disp = wind_dispersal_factor(wind_speed)              # scalar 0–1

        # Vectorised direction factor for all cells simultaneously
        dir_factor = wind_direction_factor_vec(
            cell_lats, cell_lons, t_lats, t_lons, nearest_idx, wind_deg
        )  # (N,), in [-1, 1]

        wind_adj = dir_factor * disp * WIND_WEIGHT            # (N,) µg/m³

    # --- Apply and clamp ---
    # traffic_adj is always positive (adds pollution near congested roads).
    # wind_adj is positive when wind disperses (subtract) and negative when
    # it transports pollution toward the cell (subtract a negative = add).
    adjusted = flat_vals + traffic_adj - wind_adj
    adjusted  = np.clip(adjusted, 0.0, None)

    return adjusted.reshape(grid_values.shape)
