"""
Tests for `engine.interpolation` — locks in the IDW math the rest of the
system depends on. Documents current behaviour; not a place to fix bugs.

The IDW formula and constants are reproduced inline from
`ALGORITHMS.md §3` so a future regression caused by a change in
config.IDW_POWER, config.IDW_SEARCH_RADIUS_DEG, or config.LON_CORRECTION
trips one of these tests rather than silently shifting the heatmap.

`run_idw` calls `compute_distance_to_highway` for each input sensor; the
OSMnx cache at `data/.cache/dfw_highways.pkl` is expected to exist
(populated by earlier sessions). If it doesn't, the first test in this
file pays a one-time ~30s OSMnx fetch.
"""

import numpy as np
import pandas as pd
import pytest

from config import (
    BBOX,
    IDW_POWER,
    IDW_SEARCH_RADIUS_DEG,
    LON_CORRECTION,
)
from engine.interpolation import run_idw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sensor_df(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """Build a sensor DataFrame from (lat, lon, pm25) tuples."""
    return pd.DataFrame(
        [{"lat": la, "lon": lo, "pm25": pm} for la, lo, pm in rows]
    )


def _idw_at(query_lat: float, query_lon: float,
            sensors: list[tuple[float, float, float]]) -> float:
    """Reference IDW implementation — direct transcription of the formula
    in ALGORITHMS.md §3. Used as the expected value for run_idw output."""
    weighted_sum = 0.0
    weight_total = 0.0
    for s_lat, s_lon, s_pm in sensors:
        dlat = query_lat - s_lat
        dlon = (query_lon - s_lon) * LON_CORRECTION
        dist = np.sqrt(dlat ** 2 + dlon ** 2)
        if dist > IDW_SEARCH_RADIUS_DEG:
            continue
        # Match the divide-by-zero guard in engine/interpolation.py.
        if dist == 0:
            dist = 1e-10
        w = 1.0 / (dist ** IDW_POWER)
        weighted_sum += w * s_pm
        weight_total += w
    if weight_total == 0:
        # Fallback: global mean of all sensors.
        return float(np.mean([pm for _, _, pm in sensors]))
    return weighted_sum / weight_total


def _grid_index_for(lat: float, lon: float, resolution: int) -> tuple[int, int]:
    """Mirror of run_idw's linspace grid: returns the (row, col) of the
    cell whose centre is closest to (lat, lon)."""
    lats = np.linspace(BBOX["south"], BBOX["north"], resolution)
    lons = np.linspace(BBOX["west"], BBOX["east"], resolution)
    i = int(np.argmin(np.abs(lats - lat)))
    j = int(np.argmin(np.abs(lons - lon)))
    return i, j


# ---------------------------------------------------------------------------
# Core IDW math
# ---------------------------------------------------------------------------

def test_idw_at_known_query_point_matches_hand_computed_value():
    """Three sensors arranged around the bbox centre; the IDW value at
    that centre cell must match the formula evaluated independently.

    With IDW_POWER=3 and the cosine-corrected metric, the centre cell
    (32.815, -96.755) sees S1 and S2 (both 0.055° east/west, equal
    weight) and S3 (0.055° north, slightly farther in corrected
    distance and so less weight). The weighted average is independently
    computed by `_idw_at` to produce the expected value."""
    # grid_resolution=11 places one cell exactly at the bbox centre.
    resolution = 11
    sensors = [
        (32.815, -96.700, 10.0),  # east of centre
        (32.815, -96.810, 20.0),  # west of centre
        (32.870, -96.755, 30.0),  # north of centre
    ]
    df = _sensor_df(sensors)

    _, _, idw_grid, _, _ = run_idw(df, grid_resolution=resolution)

    centre_lat, centre_lon = 32.815, -96.755
    i, j = _grid_index_for(centre_lat, centre_lon, resolution)
    expected = _idw_at(centre_lat, centre_lon, sensors)

    assert idw_grid[i, j] == pytest.approx(expected, rel=1e-9)


def test_idw_query_coincident_with_sensor_returns_sensor_value():
    """A query point sitting exactly on a sensor must return that
    sensor's pm25 (modulo the divide-by-zero guard). The 1e-10 distance
    floor makes the colocated sensor's weight ~10^30× larger than any
    other sensor's, so the weighted average collapses to its value."""
    resolution = 11
    # Centre of the bbox at resolution=11 lands exactly at (32.815, -96.755).
    sensors = [
        (32.815, -96.755, 42.0),  # colocated with the centre cell
        (32.870, -96.700, 10.0),  # nearby distractor
        (32.760, -96.810, 18.0),  # nearby distractor
    ]
    df = _sensor_df(sensors)

    _, _, idw_grid, _, _ = run_idw(df, grid_resolution=resolution)
    i, j = _grid_index_for(32.815, -96.755, resolution)

    # Tolerance is loose because the 1e-10 guard isn't an exact zero
    # — the distractors contribute a tiny fraction. In practice the
    # difference is well below 1e-15.
    assert idw_grid[i, j] == pytest.approx(42.0, abs=1e-9)


def test_idw_outside_search_radius_falls_back_to_global_mean():
    """A grid cell with no sensors within IDW_SEARCH_RADIUS_DEG must
    fall back to the unweighted mean of all sensors. We arrange this by
    clustering all sensors near the NE corner of the bbox and querying
    the SW corner cell (~0.7° away — well outside the 0.15° radius)."""
    resolution = 5  # corners are exact bbox corners at resolution=5

    sensors = [
        (33.07, -96.47, 42.0),
        (33.07, -96.49, 18.0),
        (33.05, -96.48, 30.0),
    ]
    df = _sensor_df(sensors)
    expected_mean = float(np.mean([pm for _, _, pm in sensors]))

    _, _, idw_grid, _, _ = run_idw(df, grid_resolution=resolution)

    # SW corner cell at resolution=5 → row 0, col 0 (bbox south, west).
    sw_value = idw_grid[0, 0]
    assert sw_value == pytest.approx(expected_mean, rel=1e-9), (
        f"SW corner {(BBOX['south'], BBOX['west'])} must hit the global-mean "
        f"fallback when all sensors are clustered near the NE corner"
    )


def test_idw_cosine_correction_makes_east_sensor_closer_than_north_sensor():
    """At Dallas latitude, 1° lon ≈ 0.84° lat in true distance. So a
    sensor 0.05° east of the query sits at a smaller corrected distance
    than a sensor 0.05° north of it, and gets a larger IDW weight.

    With both sensors at the same pm25, a query value identical to that
    pm25 doesn't tell us much. Set them to *different* pm25 values: the
    east sensor's larger weight pulls the IDW value toward its reading.
    """
    resolution = 11
    centre_lat, centre_lon = 32.815, -96.755

    # East sensor and north sensor at equal raw degree distance (0.05°).
    east_pm = 10.0
    north_pm = 30.0
    sensors = [
        (centre_lat,         centre_lon + 0.05, east_pm),   # east, 0.05° lon
        (centre_lat + 0.05,  centre_lon,        north_pm),  # north, 0.05° lat
    ]
    df = _sensor_df(sensors)

    _, _, idw_grid, _, _ = run_idw(df, grid_resolution=resolution)
    i, j = _grid_index_for(centre_lat, centre_lon, resolution)
    value = idw_grid[i, j]

    # If the cosine correction were missing (raw degree distance), both
    # sensors would have equal weight and the value would be (10+30)/2 = 20.
    # With LON_CORRECTION ≈ 0.84, the east sensor's effective distance is
    # 0.05*0.84 = 0.042 vs the north sensor's 0.05 — the east sensor
    # weighs ~(0.05/0.042)^3 = ~1.69× more, pulling the value toward 10.
    assert value < 20.0, (
        f"cosine correction should pull the value below the un-corrected mean of 20; got {value}"
    )

    # Sanity: the value must still lie between the two sensor pm25 values.
    assert east_pm < value < north_pm


# ---------------------------------------------------------------------------
# Output shape and bounds
# ---------------------------------------------------------------------------

def test_run_idw_returns_arrays_of_requested_resolution():
    """run_idw(grid_resolution=10, ...) must return arrays shaped (10, 10)
    for every component of the tuple."""
    sensors = [
        (32.78, -96.80, 12.0),
        (32.85, -96.70, 20.0),
        (32.70, -96.85, 8.0),
    ]
    df = _sensor_df(sensors)

    lats_2d, lons_2d, idw_grid, hw_dist, confidence = run_idw(df, grid_resolution=10)

    for arr, name in [
        (lats_2d, "lats_2d"),
        (lons_2d, "lons_2d"),
        (idw_grid, "idw_grid"),
        (hw_dist, "hw_dist"),
        (confidence, "confidence"),
    ]:
        assert arr.shape == (10, 10), f"{name} expected (10,10), got {arr.shape}"


def test_run_idw_grid_values_are_non_negative():
    """PM2.5 is non-negative by physics. With non-negative sensor inputs,
    no IDW cell should come back negative — both inside the search radius
    (where the result is a positive-weighted average of non-negative
    inputs) and outside (where the global-mean fallback kicks in)."""
    sensors = [
        (32.78, -96.80, 5.0),
        (32.85, -96.70, 12.0),
        (32.70, -96.85, 3.0),
        (32.95, -96.55, 25.0),
    ]
    df = _sensor_df(sensors)

    _, _, idw_grid, _, _ = run_idw(df, grid_resolution=15)

    assert (idw_grid >= 0).all(), (
        f"IDW produced {(idw_grid < 0).sum()} negative cells — pm25 must be non-negative"
    )
