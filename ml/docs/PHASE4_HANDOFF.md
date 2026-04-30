# Phase 4 Handoff — Training Data Collection Status

> Hand this file to Claude to pick up where the last session left off. Read CLAUDE.md first for project-wide context.

---

## Where we are

The Phase 4 training-data pipeline (`data/collect_training_data.py`) was smoke-tested end-to-end against 1-day and 7-day windows. It works. A data-quality issue was found, diagnosed, and fixed before committing to the full 180-day pull. **No 180-day collection has been run yet** — that's the next step.

## What we ran

| Run | Args | Result | Notes |
|---|---|---|---|
| Smoke test 1 | `--days 1` | 411 rows, 21 sensors | Pipeline works end-to-end |
| Smoke test 2 | `--days 7` | 2,644 rows, 21 sensors | A/B drop rate **36.2%** — too high |
| After fix | `--days 7 --resume` | 2,814 rows, 18 sensors | A/B drop **32.4%**, broken sensors removed |

## What we found

A per-sensor A/B-disagreement breakdown showed the loss was concentrated, not distributed:

- **8 sensors** had A/B failure rates of 80–100% (median disagreement 50–200%) — these are broken hardware, one dead/miscalibrated laser
- **18 sensors** had median disagreement <10% and near-zero drop rates
- **1 sensor** (120681) sat on the borderline (43% drops, median 26%)

Letting individual rows from broken sensors slip through the 30% threshold contaminates the training set even when those particular rows happen to pass.

## What we changed

`data/collect_training_data.py`:

1. **Loosened row-level threshold** `AB_DISAGREEMENT_THRESHOLD` from `0.30` → `0.50`. The 30% bar was overly strict relative to EPA AirNow's published guidance (closer to "5 µg/m³ or 70%").
2. **Added sensor-level filter** `SENSOR_AB_FAILURE_RATE_MAX = 0.50`. Any sensor where >50% of rows fail A/B at the row threshold gets dropped wholesale (broken hardware shouldn't contribute any rows).
3. **`validate_ab_channels()`** now does both stages and logs the dropped sensor IDs.
4. **`QualityReport`** now tracks `sensors_dropped_ab_failure` and `sensors_dropped_ab_failure_ids` for audit.

The 8 sensors dropped at 7 days:
`[12969, 53365, 87721, 90785, 123409, 128645, 280474, 280940]`

These IDs are also written to `data/quality_report.json` on every run.

## Open questions / decisions to make

1. **Run the 180-day collection.** Command: `python data/collect_training_data.py --days 180`. Will take meaningfully longer than the 7-day run (~30s scaled to ~13min of API calls; in practice closer to 15–20min with PurpleAir's chunked 14-day windows). Run from project root with the venv activated.
2. **Re-check the bad-sensor list at 180 days.** The set of broken sensors at 180 days will likely overlap with but not equal the 7-day list. Check `quality_report.json["sensors_dropped_ab_failure_ids"]` after the run. If the count balloons (e.g. >12 sensors dropped of 27), revisit thresholds before training.
3. **Borderline sensor 120681.** At 7 days it had a 43% drop rate at the 30% threshold but passed the 50% threshold and survived sensor-level filtering. Worth eyeballing in the 180-day run — if it stays high, consider tightening `SENSOR_AB_FAILURE_RATE_MAX` to 0.40.
4. **Planned refactor** (CLAUDE.md notes this): extract `apply_epa_correction()` into a shared `data/corrections.py` so `data/purpleair.py` (live) and `data/collect_training_data.py` (training) stop duplicating the formula. Not blocking Phase 4.

## How to verify the next 180-day run looks healthy

After running `python data/collect_training_data.py --days 180`:

```bash
cat data/quality_report.json
```

Sanity checks:
- `final_row_count` should be in the rough ballpark of `(27 - sensors_dropped_ab_failure) * 24 * 180 * (1 - drop_rate)` — e.g. ~70-90k rows
- `sensors_dropped_ab_failure` should be ≤12 (out of 27)
- `wind_hours_gap_filled` should be small relative to `wind_hours_available`
- `rows_dropped_out_of_range` should be a small fraction of `raw_purpleair_rows`
- `epa_correction_applied: true` and the per-row humidity coverage in the log should be high

Then: spot-check `data/history.csv` — column schema, no all-NaN columns, plausible PM2.5 distribution.

## Current state of files

- `data/history.csv` — currently holds the 7-day run output (2,814 rows, 18 sensors). Will be **overwritten** by the next run.
- `data/.checkpoints/` — 27 parquet files for the 7-day window. Will be reused if you `--resume` a 7-day run, but a 180-day run needs fresh checkpoints (delete the directory first).
- `data/collection_log.txt` — appends every run; safe to leave.
- `data/quality_report.json` — overwritten each run.

## Key things not to break

- The training-set column schema is the long-term standard (CLAUDE.md): `sensor_id`, `lat`, `lon`, `dist_to_highway_m`, `pm25`, `pm25_raw`, `epa_corrected`, `source`, `humidity`, `wind_speed`, `wind_deg`, `local_hour_of_day`, `day_of_week`, `is_weekend`, `is_am_rush`, `is_pm_rush`, `traffic_index`. Don't rename these or mix in the live-only feature columns from `engine/features.py`. `dist_to_highway_m` is a static spatial feature pulled from OSMnx — to widen the highway set, edit `HIGHWAY_FILTER` in `data/spatial_features.py`; the next run will refetch and recache automatically.
- The EPA correction formula must stay identical in `data/purpleair.py` and `data/collect_training_data.py` until the corrections.py refactor lands.
- Sensor readings are never traffic/wind-adjusted — only post-IDW grid cells are.
