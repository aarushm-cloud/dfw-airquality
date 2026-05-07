"""
Tests for `data.ingestion.history` — covers audit issues #7 (local hour
of day) and #16 (COLUMNS schema derivation).

Why these are tested together: both bugs share a root cause, the
hand-maintained list of column names, and both fixes are in the same
file. Running them together also catches drift between the two — e.g. if
someone renames `local_hour_of_day` they should see one test break, not
two unrelated tests.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

import data.ingestion.history as history
from data.ingestion.history import (
    COLUMNS,
    DALLAS_TZ,
    _build_snapshot_record,
    _empty_record_template,
    save_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_sensor_df() -> pd.DataFrame:
    """Mimic the output of build_features() for a single sensor."""
    return pd.DataFrame([{
        "sensor_id": 1,
        "lat":       32.78,
        "lon":      -96.80,
        "pm25":      12.5,
        "pm25_raw":  13.0,
        "epa_corrected": 1,
        "source":    "purpleair",
        # Feature columns produced by engine.features.build_features:
        "traffic_factor":     0.0,
        "wind_term":          0.0,
        "nearest_congestion": 0.0,
        "distance_to_road_m": 100.0,
        "direction_factor":   0.0,
        "dispersal":          0.5,
    }])


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """Redirect HISTORY_PATH to a temp file so the test never touches the
    real dashboard_snapshots.csv. Yields the path."""
    target = tmp_path / "snap.csv"
    monkeypatch.setattr(history, "HISTORY_PATH", str(target))
    return target


# ---------------------------------------------------------------------------
# Audit #7: local_hour_of_day must be Dallas time, not UTC
# ---------------------------------------------------------------------------

def test_local_hour_of_day_is_dallas_local(isolated_history):
    """2026-05-07 14:00 UTC = 2026-05-07 09:00 in America/Chicago (CDT).
    The snapshot must record 9, not 14."""
    ts_utc = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                  {"wind_speed": 0, "wind_deg": None}, timestamp=ts_utc)

    df = pd.read_csv(isolated_history)
    assert df["local_hour_of_day"].iloc[0] == 9


def test_day_of_week_is_dallas_local(isolated_history):
    """Snapshot at 03:00 UTC Saturday = 22:00 Friday in Dallas. day_of_week
    should record Friday (4), not Saturday (5)."""
    # 2026-05-09 (Saturday) at 03:00 UTC = 2026-05-08 22:00 CDT (Friday)
    ts_utc = datetime(2026, 5, 9, 3, 0, 0, tzinfo=timezone.utc)
    save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                  {"wind_speed": 0, "wind_deg": None}, timestamp=ts_utc)

    df = pd.read_csv(isolated_history)
    # Python weekday(): Monday=0 ... Sunday=6, so Friday=4.
    assert df["day_of_week"].iloc[0] == 4


def test_old_hour_of_day_column_no_longer_exists(isolated_history):
    """Regression: the legacy `hour_of_day` column must be gone from new snapshots."""
    ts = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                  {"wind_speed": 0, "wind_deg": None}, timestamp=ts)

    df = pd.read_csv(isolated_history)
    assert "hour_of_day" not in df.columns
    assert "local_hour_of_day" in df.columns


def test_naive_timestamp_is_rejected():
    """A naive datetime would be silently treated as host-local time by
    astimezone(); we'd rather fail loudly."""
    naive_ts = datetime(2026, 5, 7, 14, 0, 0)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                      {"wind_speed": 0, "wind_deg": None}, timestamp=naive_ts)


# ---------------------------------------------------------------------------
# Audit #16: COLUMNS must be derived from the record builder, not drift
# ---------------------------------------------------------------------------

def test_columns_constant_matches_csv_header(isolated_history):
    """If COLUMNS and the on-disk header don't agree, downstream readers
    will mis-align. This is the canonical regression for #16."""
    ts = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                  {"wind_speed": 0, "wind_deg": None}, timestamp=ts)

    df = pd.read_csv(isolated_history)
    assert list(df.columns) == list(COLUMNS)


def test_columns_is_derived_from_record_builder():
    """The schema source-of-truth lives in `_build_snapshot_record`. COLUMNS
    must be a faithful projection of one of its outputs — not a hand-typed
    parallel list. This is the structural fix for #16."""
    template = _empty_record_template()
    assert COLUMNS == list(template.keys())


def test_save_snapshot_asserts_on_schema_drift(isolated_history, monkeypatch):
    """Demonstrate the safety net: if the record builder is changed in a way
    that makes its keys diverge from COLUMNS, save_snapshot should refuse
    rather than silently writing a malformed CSV."""

    real_builder = history._build_snapshot_record

    def drifted_builder(*args, **kwargs):
        record = real_builder(*args, **kwargs)
        # Simulate someone adding a new key without updating the record schema.
        record["a_new_feature_someone_forgot"] = 1.23
        return record

    monkeypatch.setattr(history, "_build_snapshot_record", drifted_builder)

    ts = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(AssertionError, match="schema drifted"):
        save_snapshot(_minimal_sensor_df(), pd.DataFrame(),
                      {"wind_speed": 0, "wind_deg": None}, timestamp=ts)


def test_empty_sensor_df_writes_nothing(isolated_history):
    """Snapshot with no sensors must not create or modify the file."""
    ts = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    save_snapshot(pd.DataFrame(), pd.DataFrame(),
                  {"wind_speed": 0, "wind_deg": None}, timestamp=ts)
    assert not isolated_history.exists()


def test_record_builder_is_pure_for_a_fixed_input():
    """Calling the record builder twice with identical inputs must produce
    identical dicts. This is what makes _empty_record_template a stable
    source of truth for COLUMNS."""
    sensor = _minimal_sensor_df().iloc[0]
    ts = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)

    a = _build_snapshot_record(ts, sensor, wind_speed=3.0, wind_deg=180.0)
    b = _build_snapshot_record(ts, sensor, wind_speed=3.0, wind_deg=180.0)
    assert a == b
    assert list(a.keys()) == list(b.keys())  # order, not just contents


# ---------------------------------------------------------------------------
# Round-trip sanity
# ---------------------------------------------------------------------------

def test_multiple_snapshots_accumulate(isolated_history):
    """Two consecutive snapshots produce two CSV rows with one shared header."""
    ts1 = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 5, 7, 15, 0, 0, tzinfo=timezone.utc)
    wind = {"wind_speed": 0, "wind_deg": None}

    save_snapshot(_minimal_sensor_df(), pd.DataFrame(), wind, timestamp=ts1)
    save_snapshot(_minimal_sensor_df(), pd.DataFrame(), wind, timestamp=ts2)

    df = pd.read_csv(isolated_history)
    assert len(df) == 2
    # Hours are local — 9 and 10 in CDT for 14:00 and 15:00 UTC.
    assert sorted(df["local_hour_of_day"].tolist()) == [9, 10]
