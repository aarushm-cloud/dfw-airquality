"""
Tests for `engine.adjustments` — locks in the traffic and wind math.

The functions in this module are pure helpers (no I/O, no global
state) and feed both `engine.features.build_features` (per-sensor) and
`engine.interpolation.adjust_grid` (per-cell). Vectorised counterparts
exist for the grid path; tests assert scalar/vec parity so a future
optimisation in one path can't drift away from the other.

The wind-direction sign verification block formerly at
`engine/features.py:157-173` (a `__main__` printout) is reproduced
here as `test_wind_direction_factor_transport_is_negative_one`.
"""

import numpy as np
import pandas as pd
import pytest

from config import LON_CORRECTION, TRAFFIC_DECAY_RADIUS_M
from engine.adjustments import (
    TRAFFIC_THRESHOLD,
    TRAFFIC_CURVE_K,
    WIND_SPEED_CAP,
    WIND_WEIGHT,
    nearest_traffic_point,
    traffic_decay_multiplier,
    traffic_factor,
    traffic_factor_vec,
    wind_direction_factor,
    wind_direction_factor_vec,
    wind_dispersal_factor,
)


# ---------------------------------------------------------------------------
# traffic_factor — the exponential congestion curve
# ---------------------------------------------------------------------------

def test_traffic_factor_below_threshold_returns_zero():
    """Congestion below TRAFFIC_THRESHOLD (0.3) is treated as no traffic."""
    assert traffic_factor(0.2) == 0.0


def test_traffic_factor_at_threshold_returns_zero():
    """Right at the threshold, the rescaled exponent is 0 → factor 0."""
    assert traffic_factor(TRAFFIC_THRESHOLD) == pytest.approx(0.0, abs=1e-12)


def test_traffic_factor_at_unity_returns_one():
    """Maximum congestion → factor saturates at 1.0."""
    assert traffic_factor(1.0) == pytest.approx(1.0, rel=1e-9)


def test_traffic_factor_matches_analytical_curve_at_midpoint():
    """A mid value must match `(exp(k*s) - 1) / (exp(k) - 1)` where
    `s = (c - threshold) / (1 - threshold)` and k = TRAFFIC_CURVE_K.

    Picking c=0.65 puts s exactly at 0.5, which is a clean reference
    point for the analytical formula (no ambiguity from rounding
    threshold inputs)."""
    c = 0.65
    s = (c - TRAFFIC_THRESHOLD) / (1.0 - TRAFFIC_THRESHOLD)
    expected = (np.exp(TRAFFIC_CURVE_K * s) - 1.0) / (np.exp(TRAFFIC_CURVE_K) - 1.0)
    assert traffic_factor(c) == pytest.approx(expected, rel=1e-9)


def test_traffic_factor_scalar_vec_parity():
    """traffic_factor (scalar) and traffic_factor_vec (vectorised) must
    agree on every input. If a future optimisation in either path
    introduces a different rounding or curve, this catches it."""
    inputs = np.array([0.0, 0.1, 0.2, TRAFFIC_THRESHOLD, 0.4, 0.5, 0.65, 0.8, 0.95, 1.0])
    looped = np.array([traffic_factor(float(c)) for c in inputs])
    vectorised = traffic_factor_vec(inputs)
    np.testing.assert_allclose(looped, vectorised, rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# traffic_decay_multiplier — linear falloff over 500m
# ---------------------------------------------------------------------------

def test_traffic_decay_multiplier_at_zero_returns_one():
    """Zero distance from a road → full traffic effect."""
    assert traffic_decay_multiplier(0.0) == pytest.approx(1.0)


def test_traffic_decay_multiplier_at_radius_boundary_returns_zero():
    """At exactly TRAFFIC_DECAY_RADIUS_M (500m), the linear ramp hits zero.
    Convert metres → degrees because the helper takes degree distance."""
    deg_at_radius = TRAFFIC_DECAY_RADIUS_M / 111_000
    assert traffic_decay_multiplier(deg_at_radius) == pytest.approx(0.0, abs=1e-12)


def test_traffic_decay_multiplier_at_midpoint_is_half():
    """Half the decay radius (~250m) → half effect remaining."""
    deg_at_half = (TRAFFIC_DECAY_RADIUS_M / 2.0) / 111_000
    assert traffic_decay_multiplier(deg_at_half) == pytest.approx(0.5, rel=1e-9)


def test_traffic_decay_multiplier_beyond_radius_clamps_to_zero():
    """Beyond the decay radius, the linear ramp would go negative — must
    be clamped at 0 (sensors / cells past the radius get *no* traffic
    bump, never a negative one)."""
    deg_beyond = (TRAFFIC_DECAY_RADIUS_M * 2.0) / 111_000
    assert traffic_decay_multiplier(deg_beyond) == 0.0


# ---------------------------------------------------------------------------
# nearest_traffic_point — uses the cosine-corrected metric
# ---------------------------------------------------------------------------

def test_nearest_traffic_point_picks_closest_under_corrected_metric():
    """The helper must pick the closest point under the same
    cosine-corrected distance the rest of the system uses, and return
    the corrected degree distance back to the caller."""
    query_lat, query_lon = 32.80, -96.80

    traffic_df = pd.DataFrame([
        {"lat": 32.80, "lon": -96.81, "congestion": 0.5},   # 0.01° west
        {"lat": 32.81, "lon": -96.80, "congestion": 0.7},   # 0.01° north
        {"lat": 33.00, "lon": -96.80, "congestion": 0.9},   # far north
    ])

    nearest, dist = nearest_traffic_point(query_lat, query_lon, traffic_df)

    # Under the cosine-corrected metric, 0.01° lon ≈ 0.0084° true vs
    # 0.01° lat = 0.01° true, so the WEST point (row 0) is closer.
    assert nearest["congestion"] == 0.5
    expected_dist = abs(0.01 * LON_CORRECTION)
    assert dist == pytest.approx(expected_dist, rel=1e-9)


# ---------------------------------------------------------------------------
# wind_dispersal_factor — square-root saturation curve
# ---------------------------------------------------------------------------

def test_wind_dispersal_factor_zero_returns_zero():
    """Calm wind → no dispersal."""
    assert wind_dispersal_factor(0.0) == 0.0


def test_wind_dispersal_factor_at_cap_returns_one():
    """Wind at WIND_SPEED_CAP (15 m/s) saturates the curve at 1.0."""
    assert wind_dispersal_factor(WIND_SPEED_CAP) == pytest.approx(1.0)


def test_wind_dispersal_factor_at_half_cap_is_root_half():
    """The square-root curve at half cap returns sqrt(0.5) ≈ 0.707.
    Pinning this exact value catches any change to the exponent."""
    assert wind_dispersal_factor(WIND_SPEED_CAP / 2.0) == pytest.approx(
        np.sqrt(0.5), rel=1e-9,
    )


def test_wind_dispersal_factor_above_cap_clips_to_one():
    """Wind faster than the cap doesn't disperse harder — clipped at 1.0."""
    assert wind_dispersal_factor(WIND_SPEED_CAP * 2.0) == 1.0


# ---------------------------------------------------------------------------
# wind_direction_factor — per-cell cosine alignment with the wind vector
# ---------------------------------------------------------------------------

def test_wind_direction_factor_perpendicular_is_zero():
    """When the bearing from traffic-point to query is perpendicular to
    the wind direction, the cosine alignment is 0 → factor 0."""
    # Sensor north of traffic point. Wind blows east-to-west (270°
    # FROM, so blowing toward 90° east). Bearing traffic→sensor is
    # straight north (0°) — perpendicular to wind.
    sensor_lat, sensor_lon = 32.81, -96.80
    nearest = pd.Series({"lat": 32.80, "lon": -96.80, "congestion": 0.7})
    wind_deg = 270.0  # wind from west, blowing east

    factor = wind_direction_factor(sensor_lat, sensor_lon, nearest, wind_deg)
    assert factor == pytest.approx(0.0, abs=1e-12)


def test_wind_direction_factor_dispersal_is_positive_one():
    """Wind blowing pollution AWAY from the sensor → factor +1.

    Sensor west of traffic; wind blows from east to west — i.e. wind
    blows from the sensor side past the traffic source and onward,
    carrying pollution away from the sensor. Per the function's sign
    convention (+1 = dispersal), factor is +1.
    """
    # Sensor is east of traffic; wind blows toward east (90° wind FROM
    # west, blows toward 90°). Wait — if sensor is east of traffic and
    # wind blows east, pollution goes TOWARD the sensor (transport).
    # Flip: sensor is east, but wind blows toward west (90° FROM east).
    # Then wind blows pollution from the source AWAY from (toward west,
    # away from the eastern sensor) → dispersal.
    sensor_lat, sensor_lon = 32.80, -96.80   # east of traffic
    nearest = pd.Series({"lat": 32.80, "lon": -96.81, "congestion": 0.7})
    wind_deg = 90.0  # wind from east → blowing toward west, away from sensor

    factor = wind_direction_factor(sensor_lat, sensor_lon, nearest, wind_deg)
    assert factor == pytest.approx(1.0, rel=1e-9)


def test_wind_direction_factor_transport_is_negative_one():
    """The verification block originally lived as a `__main__` printout
    in `engine/features.py`. Reproduced here as a regression test.

    Setup: sensor east of traffic source. Wind comes FROM the west
    (270°) → blowing east → carrying pollution from the source toward
    the sensor. Per the function's sign convention (-1 = transport
    toward sensor), factor is -1, and `wind_term = factor * disp *
    WIND_WEIGHT` is negative — so subtracting it INCREASES the
    sensor's pm25, which is what we want when wind transports
    pollution onto a sensor.
    """
    sensor_lat, sensor_lon = 32.80, -96.80
    traffic_lat, traffic_lon = 32.80, -96.81
    nearest = pd.Series({"lat": traffic_lat, "lon": traffic_lon, "congestion": 0.8})
    wind_deg = 270.0   # wind from west → blowing east, toward the sensor

    factor = wind_direction_factor(sensor_lat, sensor_lon, nearest, wind_deg)
    assert factor == pytest.approx(-1.0, rel=1e-9)

    # Knock-on contract: with disp > 0 and WIND_WEIGHT > 0, the
    # subtractive wind_term must be negative — subtracting a negative
    # increases pm25 (transport effect).
    disp = wind_dispersal_factor(5.0)
    wind_term = factor * disp * WIND_WEIGHT
    assert wind_term < 0


def test_wind_direction_factor_colocated_returns_zero():
    """If the query point is essentially on top of the traffic source
    (distance < 1e-6), bearing is undefined and the factor is 0."""
    sensor_lat, sensor_lon = 32.80, -96.80
    # Same coords (delta = 0 exactly).
    nearest = pd.Series({"lat": 32.80, "lon": -96.80, "congestion": 0.5})

    factor = wind_direction_factor(sensor_lat, sensor_lon, nearest, wind_deg=180.0)
    assert factor == 0.0


def test_wind_direction_factor_scalar_vec_parity():
    """Vectorised wind_direction_factor_vec must agree with the scalar
    helper on every input it processes. We feed the same (sensor,
    traffic, wind) configuration through both paths and compare.

    Scalar API: (point_lat, point_lon, nearest_row_series, wind_deg)
    Vector API: (cell_lats, cell_lons, t_lats, t_lons, nearest_idx, wind_deg)
    """
    # Three (cell, traffic) pairs: cell-east-of-traffic, cell-north,
    # cell-southwest. Each cell pairs with a different traffic point
    # to exercise the nearest_idx machinery in the vec path.
    cells = [
        (32.80, -96.80),   # east of traffic[0]
        (32.81, -96.79),   # north-east of traffic[1]
        (32.79, -96.81),   # south-west of traffic[2]
    ]
    traffic_pts = [
        (32.80, -96.81),
        (32.80, -96.80),
        (32.80, -96.80),
    ]
    wind_deg = 270.0

    cell_lats = np.array([c[0] for c in cells])
    cell_lons = np.array([c[1] for c in cells])
    t_lats = np.array([t[0] for t in traffic_pts])
    t_lons = np.array([t[1] for t in traffic_pts])
    nearest_idx = np.arange(len(cells))  # cell i pairs with traffic_pts[i]

    vec = wind_direction_factor_vec(
        cell_lats, cell_lons, t_lats, t_lons, nearest_idx, wind_deg,
    )

    scalar = np.array([
        wind_direction_factor(
            cell_lats[i], cell_lons[i],
            pd.Series({"lat": t_lats[i], "lon": t_lons[i]}),
            wind_deg,
        )
        for i in range(len(cells))
    ])

    np.testing.assert_allclose(vec, scalar, rtol=1e-12, atol=1e-12)
