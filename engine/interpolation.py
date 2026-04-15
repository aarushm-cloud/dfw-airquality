# engine/interpolation.py — IDW (Inverse Distance Weighting) interpolation
#
# For each point on a grid, computes a weighted average of all sensor PM2.5 values.
# Sensors closer to a grid point get more weight: weight = 1 / distance^IDW_POWER
# A search radius (IDW_SEARCH_RADIUS_DEG) limits which sensors contribute to each
# cell — distant sensors get zero weight rather than a tiny but nonzero pull.
# Result: a smooth PM2.5 surface over Dallas we can render as a heatmap.

import numpy as np
import pandas as pd

from config import BBOX, LON_CORRECTION, IDW_POWER, IDW_SEARCH_RADIUS_DEG


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
