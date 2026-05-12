import numpy as np
import pandas as pd

from data.ingestion.purpleair import (
    PM25_RAW_SATURATION_THRESHOLD,
    _quarantine_saturated,
)


def _frame(rows):
    return pd.DataFrame(rows)


def test_all_healthy():
    df = _frame([
        {"sensor_id": 1, "name": "a", "pm25_raw": 5.0},
        {"sensor_id": 2, "name": "b", "pm25_raw": 50.0},
        {"sensor_id": 3, "name": "c", "pm25_raw": PM25_RAW_SATURATION_THRESHOLD},  # boundary: > not >=
    ])
    kept, dropped = _quarantine_saturated(df)
    assert len(kept) == 3
    assert dropped.empty
    assert "filter_reason" in dropped.columns


def test_one_saturated():
    df = _frame([
        {"sensor_id": 1, "name": "a", "pm25_raw": 5.0},
        {"sensor_id": 2, "name": "b", "pm25_raw": 5000.0},
    ])
    kept, dropped = _quarantine_saturated(df)
    assert list(kept["sensor_id"]) == [1]
    assert list(dropped["sensor_id"]) == [2]
    assert (dropped["filter_reason"] == "saturated_raw").all()


def test_nan_pm25_raw_is_kept():
    df = _frame([
        {"sensor_id": 1, "name": "nan-row", "pm25_raw": np.nan},
        {"sensor_id": 2, "name": "saturated", "pm25_raw": 4991.0},
    ])
    kept, dropped = _quarantine_saturated(df)
    assert 1 in set(kept["sensor_id"].tolist())
    assert list(dropped["sensor_id"]) == [2]


def test_empty_input():
    df = pd.DataFrame(columns=["sensor_id", "name", "pm25_raw"])
    kept, dropped = _quarantine_saturated(df)
    assert kept.empty
    assert dropped.empty
    assert "filter_reason" in dropped.columns
