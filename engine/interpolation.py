# engine/interpolation.py — IDW (Inverse Distance Weighting) interpolation
#
# For each point on a grid, computes a weighted average of all sensor PM2.5 values.
# Sensors closer to a grid point get more weight: weight = 1 / distance^power
# Result: a smooth PM2.5 surface over Dallas we can render as a heatmap.

import numpy as np
import pandas as pd
from config import BBOX


def run_idw(
    df: pd.DataFrame,
    grid_resolution: int = 100,
    power: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns three 2D arrays of the same shape: (lats, lons, interpolated_pm25).
    grid_resolution controls grid density (100 = 100x100 points over Dallas).
    """
    # Build a regular lat/lon grid over the Dallas bounding box
    lat_grid = np.linspace(BBOX["south"], BBOX["north"], grid_resolution)
    lon_grid = np.linspace(BBOX["west"],  BBOX["east"],  grid_resolution)
    lons_2d, lats_2d = np.meshgrid(lon_grid, lat_grid)

    sensor_lats = df["lat"].values.astype(np.float64)
    sensor_lons = df["lon"].values.astype(np.float64)
    sensor_pm25 = df["pm25"].values.astype(np.float64)

    # Reshape for numpy broadcasting: grid points (res, res, 1) vs sensors (1, 1, n)
    # This lets us compute all distances at once without a Python loop
    lats_3d = lats_2d[:, :, np.newaxis]
    lons_3d = lons_2d[:, :, np.newaxis]
    s_lats  = sensor_lats[np.newaxis, np.newaxis, :]
    s_lons  = sensor_lons[np.newaxis, np.newaxis, :]

    # Euclidean distance in degrees — sufficient for city-scale interpolation
    distances = np.sqrt((lats_3d - s_lats) ** 2 + (lons_3d - s_lons) ** 2)
    distances = np.where(distances == 0, 1e-10, distances)  # avoid divide-by-zero

    weights      = 1.0 / (distances ** power)
    weighted_sum = np.sum(weights * sensor_pm25[np.newaxis, np.newaxis, :], axis=2)
    weight_total = np.sum(weights, axis=2)

    interpolated = weighted_sum / weight_total  # shape: (grid_res, grid_res)

    return lats_2d, lons_2d, interpolated
