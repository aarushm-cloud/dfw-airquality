# Changes — schema & shared-formula hygiene pass (2026-05-07)

Closes audit issues **#1** (EPA correction duplicated), **#7** (`hour_of_day`
vs. `local_hour_of_day`), and **#16** (`COLUMNS` drift). 22 tests added,
all passing.

## Files

```
data/corrections.py                       NEW — single source of truth for
                                                the Barkjohn 2021 formula
data/ingestion/purpleair.py               MODIFIED — imports from corrections
data/ingestion/history.py                 MODIFIED — derived COLUMNS,
                                                Dallas-local hour/day
ml/training/collect_training_data.py      MODIFIED — wraps the shared
                                                function with reporting layer
tests/conftest.py                         NEW — sys.path setup
tests/test_epa_correction.py              NEW — 12 tests
tests/test_history_snapshot.py            NEW — 10 tests
```

## Behaviour changes worth flagging

### #1 — `apply_epa_correction()`

The unified function in `data/corrections.py` is a *superset* of both old
behaviours. In practice, both call sites produce byte-identical output to
their old implementations on any realistic input. The two intentional
differences are:

* The unified function clips `pm25` to `>= 0` across **all** rows (not just
  RH-corrected rows). The live path filtered negatives upstream, so this
  is a no-op there. The training path already did this same end-of-function
  clip, so this is also a no-op there.
* The unified function handles a **missing `humidity` column** gracefully
  (returns `pm25 = pm25_raw`, `epa_corrected = 0`). The training path's
  old version would have raised a `KeyError`. The live path's old version
  also handled this, so no behaviour change there. If the training path
  has been relying on the column always being present, the new behaviour
  is strictly safer.

The `report.*` counters and progress logs in the training script are
preserved by wrapping the shared call with a thin layer in
`collect_training_data.py:apply_epa_correction`.

### #7 — `local_hour_of_day` is genuinely Dallas-local

The old `hour_of_day` column stored `timestamp.hour` on a UTC datetime —
i.e. it was UTC, despite the name suggesting otherwise. The new
`local_hour_of_day` column is computed as
`timestamp.astimezone(ZoneInfo("America/Chicago")).hour`, matching what
`ml/training/collect_training_data.py:add_traffic_features` does on the
training set.

`day_of_week` is also now in Dallas-local time (it was UTC before). This
matters around midnight: a snapshot at 03:00 UTC Saturday is 22:00 Friday
in Dallas — `day_of_week` should be Friday (4), not Saturday (5). Old
snapshots in `data/dashboard_snapshots.csv` will be inconsistent with
new ones at hour boundaries; see the migration note below.

`save_snapshot()` now also rejects naive timestamps with `ValueError`
because `astimezone()` would otherwise treat them as host-local time and
silently produce wrong hours.

### #16 — `COLUMNS` is now derived

The schema is defined in `_build_snapshot_record()`. `COLUMNS` is computed
from a placeholder call to that function at import time. Adding a key to
the record builder updates `COLUMNS` automatically. `save_snapshot()`
asserts that the in-memory DataFrame columns match `COLUMNS` — if a future
edit introduces drift, the assertion fires loudly instead of silently
dropping columns.

## Things to do before merging

1. **Existing `data/dashboard_snapshots.csv` carries the old schema**
   (`hour_of_day`, UTC values). `load_history()` uses `on_bad_lines='skip'`
   so old rows will be silently skipped after the schema change — fine for
   a fresh start. If you want to keep the historical snapshots, run a
   one-time migration:

   ```python
   import pandas as pd
   from zoneinfo import ZoneInfo

   df = pd.read_csv("data/dashboard_snapshots.csv", parse_dates=["timestamp"])
   # Old hour_of_day was UTC; recompute as Dallas-local.
   ts_local = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert("America/Chicago")
   df["local_hour_of_day"] = ts_local.dt.hour
   df["day_of_week"]       = ts_local.dt.dayofweek
   df = df.drop(columns=["hour_of_day"])
   df.to_csv("data/dashboard_snapshots.csv", index=False)
   ```

   *(If `df["timestamp"]` is already tz-aware — modern pandas + ISO
   `+00:00` strings — drop `tz_localize` and use `tz_convert` directly.)*

2. **Run the test suite from the project root** so the relative imports
   resolve:

   ```bash
   pytest tests/ -v
   ```

3. The `__all__` re-export of `apply_epa_correction` from
   `data/ingestion/purpleair.py` keeps any existing
   `from data.ingestion.purpleair import apply_epa_correction` callers
   working without modification. Once you've grepped to confirm nobody
   relies on the re-export, you can drop it.

## Not in this pass (deferred)

* **#5** `dist_to_highway_m` in the live feature pipeline — Phase 4
  unblocker, but it's a real feature addition (and needs careful caching
  against the OSMnx-backed `lru_cache`), not a hygiene fix. Next session.
* **#4** `fcntl.flock` — flagged in a comment in `history.py` but not
  changed. The cross-platform `filelock` migration is its own session.
* **#8** OpenAQ naive-timestamp robustness — small fix but a different
  module; out of scope here.
