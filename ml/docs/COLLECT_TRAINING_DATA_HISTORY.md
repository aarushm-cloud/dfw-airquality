# `data/collect_training_data.py` — History & Walkthrough

This document explains, in plain English, what `data/collect_training_data.py`
does, how each step works, and the purpose of every edit the file has received
since it was first added to the repo.

---

## 1. What the file is for

`collect_training_data.py` is a **one-shot, headless data-collection script**.
Its only job is to build `data/history.csv` — the labeled training set that the
Phase 4 Random Forest PM₂.₅ model will learn from.

Earlier in the project, training rows were going to be accumulated slowly by
`data/history.py`, which appends a snapshot every time the live dashboard
refreshes. That approach works, but it would take months to build up enough
rows to train a model. This script side-steps that wait by pulling **6 months
of historical hourly data in a single run** from PurpleAir's history API,
joining it with NOAA wind data and time-based traffic proxies, and writing the
result to `history.csv` in the schema the model will expect.

The file is intentionally self-contained: it has its own logging, its own
quality report, its own retry/checkpoint logic, and runs from the command line.

---

## 2. How the file works, end to end

When you run it (e.g. `python data/collect_training_data.py --days 180`), the
script walks through six clearly-numbered steps. The numbers in the source
code (`STEP 1`, `STEP 2`, …) match this list.

### Setup (top of the file)
- **Loads the API key** from `.env` (`PURPLEAIR_API_KEY`).
- **Puts the project root on `sys.path`** so it can `from config import BBOX,
  PURPLEAIR_BASE_URL` even though the script lives inside `data/`.
- **Configures logging** to write the same messages to both the terminal and
  `data/collection_log.txt`, so a long unattended run leaves a real audit
  trail.
- **Creates a `QualityReport` dataclass** that quietly tallies counts (rows
  collected, rows dropped, sensors with no data, etc.) and gets dumped to
  `data/quality_report.json` at the end.
- **Defines `http_get_with_retry`** — a small wrapper around `requests.get`
  that retries on 5xx and 429 responses with exponential backoff. Every
  outbound HTTP call in the script goes through this helper.

### Step 1 — Discover sensors (`get_dfw_sensors`)
Calls `GET /v1/sensors` once, scoped to the DFW bounding box from `config.py`,
asking only for outdoor sensors (`location_type=0`). Returns a list of dicts
with each sensor's index, name, and lat/lon. This is the working set for Step 2.

### Step 2 — Pull each sensor's history (`fetch_sensor_history` + `collect_all_purpleair`)
For every sensor returned in Step 1, the script asks PurpleAir for hourly
PM2.5 readings (channels A and B separately, plus humidity) over the requested
date range.

Two important details:
- **2-week chunking.** PurpleAir's history endpoint caps each request at
  14 days, so the date range is sliced into two-week windows and walked
  sequentially.
- **Per-sensor checkpointing.** After each sensor finishes, its rows are
  written to `data/.checkpoints/sensor_<id>.parquet`. If you run with
  `--resume`, sensors whose checkpoint already exists are skipped — so a
  crashed run can pick up where it left off without re-paying for the API
  calls already made.

When all sensors are done, the per-sensor frames are concatenated into one
big raw DataFrame and the script moves on to cleaning.

### Step 3 — Clean the PurpleAir data
Three filters, in order:

1. **`validate_ab_channels`** — every PurpleAir sensor has two laser
   counters. EPA guidance says that if A and B disagree by more than ~30%,
   the reading is unreliable. The script drops those rows and replaces the
   two channel columns with their average (`pm25_raw`).
2. **`apply_epa_correction`** — applies the official EPA PurpleAir
   correction formula:
   `PM2.5_corrected = 0.52 * PM2.5_raw − 0.085 * RH + 5.71`
   Rows with no humidity reading fall through with the raw value and are
   flagged `epa_corrected = 0` so downstream code can choose to down-weight
   them.
3. **`filter_range`** — discards anything outside `0 ≤ PM2.5 < 500 µg/m³`.
   Negative values and 1000+ spikes are almost always sensor faults.

### Step 4 — Pull wind data (`fetch_wind_data`)
Calls **Meteostat** (a free Python wrapper around NOAA's Integrated Surface
Database) to fetch hourly wind speed and direction at DFW Airport for the
same date range. Wind speed is converted from km/h to m/s to match the rest
of the project. If Meteostat is not installed or returns nothing, the
script logs a warning and falls back to climate normals later.

### Step 5 — Engineer traffic features (`add_traffic_features`)
TomTom's free tier doesn't expose historical traffic, so the script can't
ask "how congested was this road at this exact time last March." Instead it
builds **temporal proxies** that correlate strongly with traffic in DFW:
`hour`, `day_of_week`, `is_weekend`, `is_am_rush`, `is_pm_rush`, plus a
single rolled-up `traffic_index` ∈ [0.1, 1.0]. All are computed vectorised
on the full DataFrame.

### Step 6 — Merge and write CSV (`build_final_dataset`)
- Floors PurpleAir timestamps to the hour so they line up with Meteostat's
  hourly wind grid.
- Left-joins wind onto the PurpleAir frame; gap-fills missing hours with
  forward-then-backward-fill (wind is autocorrelated hour to hour at a
  single metro), and falls back to DFW climate normals (4.5 m/s, 180°) if
  any hours remain unfilled.
- Adds the temporal traffic features.
- **Renames columns** to match the live-snapshot schema in
  `data/history.py` (`sensor_id`, `lat`, `lon`, `wind_speed`, `wind_deg`,
  `hour_of_day`) and tags every row `source = "purpleair"`.
- Sorts by `(timestamp, sensor_id)` and writes the final CSV.

### Reporting and exits
After the CSV is written, `QualityReport.save()` writes
`data/quality_report.json`. If anything raises along the way, the exception
is logged, the report is still saved (with a warning entry), and the
process exits with status 1.

---

## 3. Outputs

| File | Purpose | Tracked? |
|---|---|---|
| `data/history.csv` | Final training set — what the Phase 4 model trains on | gitignored |
| `data/collection_log.txt` | Full timestamped log of the run | gitignored |
| `data/quality_report.json` | Dataclass dump of counts, drops, warnings | gitignored |
| `data/.checkpoints/sensor_<id>.parquet` | Per-sensor resume point | gitignored |

---

## 4. Edit history

The file's git history is short — it landed as one large commit, then
received one set of uncommitted refinements on top.

### Commit `6ac269c` — "epa corrections & write collection" (2026-04-23)

The file was added in a single 662-line commit alongside related changes to
`data/purpleair.py`, `data/history.py`, `data/openaq.py`, `engine/features.py`,
and `viz/heatmap.py`.

This is the original version of the script. It contained everything described
above with two notable differences from the current code:

- **A duplicate `BBOX` dict was hard-coded at the top** of the file instead
  of being imported from `config.py`. The values matched the project bounding
  box but were copy-pasted.
- **PurpleAir URLs were string literals.** Both the sensor-list endpoint
  (`https://api.purpleair.com/v1/sensors`) and the per-sensor history
  endpoint were written out as full URLs.
- **The output schema used PurpleAir-native column names** —
  `sensor_index`, `latitude`, `longitude`, `wind_speed_ms`, `wind_dir_deg`,
  `hour` — rather than the schema used by the live `history.py` snapshot
  accumulator.
- The `get_dfw_sensors` request did **not** filter on `location_type`, so
  it could in principle pick up indoor sensors that the live dashboard
  ignores.

**Purpose of this commit:** introduce the entire batch training-data pipeline
in one piece. Up to this point Phase 4 had no concrete plan for getting a
training set; this commit makes it real and sets up the EPA-correction
plumbing alongside it (which is why `data/purpleair.py` was edited in the
same commit — both modules now share the correction formula).

### Uncommitted edits (currently in the working tree)

There are five purposeful changes on top of `6ac269c`:

1. **Use `BBOX` and `PURPLEAIR_BASE_URL` from `config.py`** instead of
   re-declaring them locally.
   *Purpose:* eliminate drift. If the dashboard's bounding box changes in
   `config.py`, the training set will follow automatically instead of
   silently using the old box.

2. **Add `location_type: 0` to the sensor-discovery request.**
   *Purpose:* match the filter `data/purpleair.py` already uses for the
   live dashboard, so the training set's sensor population is the same
   one the model will see at inference time. Indoor sensors don't belong
   in either pipeline.

3. **Add a `TODO` comment on `apply_epa_correction`.**
   *Purpose:* flag that this function is duplicated in `data/purpleair.py`
   and that both copies must be edited in lockstep. Marks a future
   refactor: extract into a shared `data/corrections.py`.

4. **Rename output columns to match `data/history.py`'s schema.**
   `sensor_index → sensor_id`, `latitude → lat`, `longitude → lon`,
   `wind_speed_ms → wind_speed`, `wind_dir_deg → wind_deg`, `hour →
   hour_of_day`.
   *Purpose:* make the historical training rows from this script and the
   live snapshot rows from `history.py` schema-compatible, so the Phase 4
   model can be trained on either one (or both concatenated) without any
   downstream rename plumbing.

5. **Add `source = "purpleair"` to every row.**
   *Purpose:* leave room for an OpenAQ-derived training set to be appended
   later. Each row stays auditable to its origin even after the two
   sources are concatenated, mirroring the `source` column the live
   pipeline already maintains.

Several of the diff's other line changes are whitespace-only (trailing
spaces stripped from blank lines) and have no functional effect.

---

## 5. Where to look next

- `config.py` — bounding box and base URL that this script now imports.
- `data/purpleair.py` — shares the `apply_epa_correction` logic; keep the
  two copies in sync until the planned `data/corrections.py` extraction.
- `data/history.py` — defines the live-snapshot schema this script's
  output now matches.
- `DFW_Algorithm_Report.md` — broader algorithmic context for Phases 1–3.
