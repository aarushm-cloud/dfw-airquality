"""
Tests for `data.corrections.apply_epa_correction`.

The point of extracting this function (audit issue #1) is that the live
ingestion pipeline and the historical training pipeline can no longer
silently drift apart. These tests exercise:

  * The reference Barkjohn 2021 formula on known inputs.
  * Both call patterns supported by the unified function — the live path
    (no `pm25_raw` column on entry) and the training path (`pm25_raw`
    pre-set by upstream A/B validation).
  * Edge cases the two old implementations handled differently:
    - `humidity` column absent entirely
    - `humidity` cell NaN
    - Negative-corrected values (low PM, high RH)
  * Side-effect freedom (must not mutate the caller's DataFrame).
"""

import numpy as np
import pandas as pd
import pytest

from data.corrections import apply_epa_correction


def _formula(pm_raw: float, rh: float) -> float:
    """Reference implementation of the Barkjohn 2021 EPA correction."""
    return 0.52 * pm_raw - 0.085 * rh + 5.71


# ---------------------------------------------------------------------------
# Formula correctness
# ---------------------------------------------------------------------------

def test_reference_value_with_humidity():
    """Sanity check: 0.52*20 - 0.085*50 + 5.71 = 11.86."""
    df = pd.DataFrame({"pm25": [20.0], "humidity": [50.0]})
    out = apply_epa_correction(df)

    assert out["pm25"].iloc[0] == pytest.approx(_formula(20.0, 50.0))
    assert out["pm25"].iloc[0] == pytest.approx(11.86, abs=1e-9)
    assert out["pm25_raw"].iloc[0] == 20.0
    assert int(out["epa_corrected"].iloc[0]) == 1


def test_zero_pm_with_high_humidity_clips_to_zero():
    """0.52*0 - 0.085*100 + 5.71 = -2.79  ->  clipped to 0."""
    df = pd.DataFrame({"pm25": [0.0], "humidity": [100.0]})
    out = apply_epa_correction(df)
    assert out["pm25"].iloc[0] == 0.0
    assert int(out["epa_corrected"].iloc[0]) == 1


def test_no_clip_when_formula_stays_positive():
    """Verify that the clip is a floor, not a ceiling — positive results pass through."""
    df = pd.DataFrame({"pm25": [50.0], "humidity": [30.0]})
    out = apply_epa_correction(df)
    assert out["pm25"].iloc[0] == pytest.approx(_formula(50.0, 30.0))


# ---------------------------------------------------------------------------
# Schema and edge cases
# ---------------------------------------------------------------------------

def test_missing_humidity_column():
    """Live path without humidity returned by the API: pm25 stays raw, flag is 0."""
    df = pd.DataFrame({"pm25": [25.0]})
    out = apply_epa_correction(df)

    assert out["pm25"].iloc[0] == 25.0
    assert out["pm25_raw"].iloc[0] == 25.0
    assert int(out["epa_corrected"].iloc[0]) == 0
    # Output must contain all three guaranteed columns regardless of input shape.
    assert {"pm25", "pm25_raw", "epa_corrected"}.issubset(out.columns)


def test_humidity_nan_falls_back_to_raw():
    """Mixed NaN humidity: corrected rows use the formula, NaN rows fall back."""
    df = pd.DataFrame({
        "pm25":     [10.0, 30.0],
        "humidity": [40.0, np.nan],
    })
    out = apply_epa_correction(df)

    assert out["pm25"].iloc[0] == pytest.approx(_formula(10.0, 40.0))
    assert out["pm25"].iloc[1] == 30.0  # raw fallback, not the formula

    assert int(out["epa_corrected"].iloc[0]) == 1
    assert int(out["epa_corrected"].iloc[1]) == 0


def test_negative_raw_reading_is_clipped():
    """A negative raw reading on a non-RH row must end up >= 0 after the function.
    The live ingestion path filters negatives upstream, but the function
    itself shouldn't propagate them."""
    df = pd.DataFrame({"pm25": [-2.0], "humidity": [np.nan]})
    out = apply_epa_correction(df)
    assert out["pm25"].iloc[0] == 0.0


def test_empty_dataframe():
    """Empty input must produce an empty DataFrame with the guaranteed columns."""
    df = pd.DataFrame({"pm25": [], "humidity": []})
    out = apply_epa_correction(df)
    assert len(out) == 0
    assert "pm25" in out.columns
    assert "pm25_raw" in out.columns
    assert "epa_corrected" in out.columns


# ---------------------------------------------------------------------------
# pm25_raw handling — the key difference between live and training paths
# ---------------------------------------------------------------------------

def test_pm25_raw_initialised_when_absent():
    """Live path: function copies pm25 -> pm25_raw on entry."""
    df = pd.DataFrame({"pm25": [25.0], "humidity": [50.0]})
    out = apply_epa_correction(df)
    # Original input is preserved as the audit trail.
    assert out["pm25_raw"].iloc[0] == 25.0
    # pm25 has been replaced with the corrected value.
    assert out["pm25"].iloc[0] == pytest.approx(_formula(25.0, 50.0))


def test_pm25_raw_preserved_when_present():
    """Training path: A/B validation sets pm25_raw upstream. The function
    must use pm25_raw as the formula input and NOT touch it."""
    df = pd.DataFrame({
        "pm25":     [99.0],   # synthetic mismatched value
        "pm25_raw": [42.0],   # what A/B validation produced
        "humidity": [50.0],
    })
    out = apply_epa_correction(df)
    # Formula uses pm25_raw, not pm25.
    assert out["pm25"].iloc[0] == pytest.approx(_formula(42.0, 50.0))
    # pm25_raw is preserved exactly.
    assert out["pm25_raw"].iloc[0] == 42.0


# ---------------------------------------------------------------------------
# Side-effect freedom and parity
# ---------------------------------------------------------------------------

def test_does_not_mutate_input():
    """Caller's DataFrame must be untouched."""
    df = pd.DataFrame({"pm25": [25.0], "humidity": [50.0]})
    snapshot = df.copy()
    _ = apply_epa_correction(df)
    pd.testing.assert_frame_equal(df, snapshot)


def test_live_and_training_call_patterns_agree():
    """The whole point of the refactor: when the inputs represent the same
    underlying readings, both call patterns must produce identical output.

    The live path supplies pm25 with the raw reading and no pm25_raw column.
    The training path supplies both pm25 and pm25_raw, with pm25_raw equal
    to the raw reading (set by A/B validation as (pm25_a + pm25_b) / 2)."""
    raw_readings = [10.0, 25.0, 50.0, 5.0]
    humidity     = [40.0, np.nan, 80.0, 100.0]

    live_input = pd.DataFrame({"pm25": raw_readings, "humidity": humidity})
    training_input = pd.DataFrame({
        "pm25":     raw_readings,    # at training-call time, pm25 == pm25_raw
        "pm25_raw": raw_readings,
        "humidity": humidity,
    })

    live_out = apply_epa_correction(live_input)
    training_out = apply_epa_correction(training_input)

    pd.testing.assert_series_equal(
        live_out["pm25"], training_out["pm25"], check_names=False
    )
    pd.testing.assert_series_equal(
        live_out["pm25_raw"], training_out["pm25_raw"], check_names=False
    )
    pd.testing.assert_series_equal(
        live_out["epa_corrected"].astype(int),
        training_out["epa_corrected"].astype(int),
        check_names=False,
    )


def test_epa_corrected_is_integer_typed():
    """Downstream code stores this column in CSV; an integer 0/1 is what's
    documented and what existing snapshots use."""
    df = pd.DataFrame({"pm25": [20.0, 30.0], "humidity": [50.0, np.nan]})
    out = apply_epa_correction(df)
    # Either int64 or a numpy integer dtype is fine; bools are not.
    assert pd.api.types.is_integer_dtype(out["epa_corrected"])
