"""
Tests for `engine.interpolation.run_idw` empty-region confidence — covers
audit issue #12.

The IDW surface uses a global-mean fallback for cells outside any
sensor's IDW_SEARCH_RADIUS_DEG. Those fallback cells must report
confidence = 0 so the dashboard can visually distinguish "we're
interpolating from real local data" from "we have no idea, here's the
metro average". A single per-refresh `WARNING` makes the count of
fallback cells visible in logs.

Note: the empty-region masking itself
(`np.where(has_neighbours, confidence, 0.0)`) was already in place
before this pass — these tests pin its behaviour against future
regression. The added observability is the new `WARNING` log assertion.
"""

import logging

import numpy as np
import pandas as pd

from config import BBOX, IDW_SEARCH_RADIUS_DEG
from engine.interpolation import run_idw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sensor_df(positions: list[tuple[float, float]], pm25: float = 10.0) -> pd.DataFrame:
    """Build a minimal sensor DataFrame from (lat, lon) pairs."""
    rows = [{"lat": la, "lon": lo, "pm25": pm25} for la, lo in positions]
    return pd.DataFrame(rows)


# Bbox is N=33.08, S=32.55 (lat span 0.53), W=-97.05, E=-96.46 (lon span 0.59).
# IDW_SEARCH_RADIUS_DEG = 0.15. So a sensor at the very north of the bbox
# cannot reach cells more than ~0.15 deg south of it.

# A small grid keeps the test fast — 10x10 is enough resolution to have both
# in-radius and out-of-radius cells without blowing test time.
GRID_RES = 10


# ---------------------------------------------------------------------------
# Empty region detection
# ---------------------------------------------------------------------------

def test_south_half_is_zero_confidence_when_sensors_only_north(caplog):
    """All sensors clustered near the north edge → southern cells are
    outside IDW_SEARCH_RADIUS_DEG and must report confidence 0. Northern
    cells should have positive confidence."""
    # Three sensors all near the north edge, spread across longitude.
    sensors = _sensor_df([
        (33.07, -96.95),
        (33.07, -96.75),
        (33.07, -96.55),
    ])

    with caplog.at_level(logging.WARNING, logger="engine.interpolation"):
        lats_2d, lons_2d, idw, hw_dist, confidence = run_idw(
            sensors, grid_resolution=GRID_RES,
        )

    # Cells where lat < (sensor_lat - search_radius) are guaranteed outside
    # the radius. With sensors at 33.07 and radius 0.15, anything south of
    # 32.92 should be zero confidence.
    south_half_mask = lats_2d < 32.85
    assert south_half_mask.any(), "test setup: south-half region must be non-empty"
    assert (confidence[south_half_mask] == 0.0).all(), (
        "south-half cells (well outside any sensor's radius) must be "
        "confidence 0, not silently positive"
    )

    # Cells very close to the sensors should have positive confidence.
    near_north = lats_2d > 33.05
    assert near_north.any(), "test setup: near-north region must be non-empty"
    assert (confidence[near_north] > 0).all(), (
        "cells close to north-clustered sensors must have positive confidence"
    )

    # And the per-refresh observability log should have fired exactly once.
    empty_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "no sensor within" in r.getMessage()
    ]
    assert len(empty_warnings) == 1, (
        f"expected exactly one IDW empty-region WARNING, got {len(empty_warnings)}"
    )


def test_full_coverage_grid_has_no_zero_confidence_cells(caplog):
    """Sensors well-distributed across the bbox → every cell sits within
    IDW_SEARCH_RADIUS_DEG of at least one sensor → zero zero-confidence
    cells. The empty-region warning must NOT fire."""
    # 5x5 grid of sensors across the bbox. Spacing ~0.13 lat × ~0.15 lon
    # means every grid cell has multiple sensors within radius.
    lats = np.linspace(BBOX["south"] + 0.02, BBOX["north"] - 0.02, 5)
    lons = np.linspace(BBOX["west"] + 0.02, BBOX["east"] - 0.02, 5)
    positions = [(la, lo) for la in lats for lo in lons]
    sensors = _sensor_df(positions)

    with caplog.at_level(logging.WARNING, logger="engine.interpolation"):
        _, _, _, _, confidence = run_idw(sensors, grid_resolution=GRID_RES)

    n_zero = int((confidence == 0.0).sum())
    assert n_zero == 0, (
        f"fully covered grid must produce 0 zero-confidence cells, got {n_zero}"
    )

    empty_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "no sensor within" in r.getMessage()
    ]
    assert empty_warnings == [], (
        "no empty-region WARNING expected when every cell has in-radius coverage"
    )


def test_confidence_values_are_in_unit_interval():
    """Confidence is documented as a 0.0–1.0 score. Verify with a trivially
    well-covered grid to make sure the clip is functioning end-to-end."""
    sensors = _sensor_df([(32.78, -96.80), (32.85, -96.70), (32.70, -96.85)])
    _, _, _, _, confidence = run_idw(sensors, grid_resolution=GRID_RES)

    assert (confidence >= 0.0).all()
    assert (confidence <= 1.0).all()
