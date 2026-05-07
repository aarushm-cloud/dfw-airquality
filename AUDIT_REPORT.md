# DFW Air Quality Dashboard — Code Audit Report

**Date:** 2026-05-07
**Scope:** Full codebase (data ingestion, engine, ml, viz, api, scripts, config, app)
**Mode:** Read-only audit. No code modified.

> **Revision (2026-05-07):** Six items in this report were independently
> verified against the actual code. Four were found to be **wrong as
> stated** (#2, #6, #10, #11), one was **theoretical only** (#3), and one
> had **smaller blast radius than claimed** (#8). The affected sections
> below are marked accordingly. Items not in {#2, #3, #6, #8, #10, #11}
> have not been re-verified and remain as originally written.

---

## Executive Summary

20 issues were originally identified; after verification, 4 are withdrawn
and 2 are downgraded. The codebase is in good shape overall — Phases 1–3
are working, the training pipeline is solid, and Phase 6 (`/api`, `/web`)
cleanly wraps the existing engine. The most pressing items are concentrated
around the **Phase 3 → Phase 4 boundary**: formula duplication between live
and training pipelines and a missing live feature (`dist_to_highway_m`)
that will block Phase 4 inference.

**Recommended fix order before starting Phase 4:**
1. Extract `apply_epa_correction()` into `data/corrections.py` (#1)
2. Add `dist_to_highway_m` to live feature pipeline (#5)
3. Rename `hour_of_day` → `local_hour_of_day` in live snapshots (#7)
4. Honor `Retry-After` in PurpleAir retries (#9)
5. Replace `fcntl.flock` with cross-platform locking (#4)
6. Make OpenAQ timestamp parsing defensive (#8 — per-location issue)

---

## Critical

### 1. EPA correction formula duplicated across two pipelines
**Files:**
- `data/ingestion/purpleair.py:26-71`
- `ml/training/collect_training_data.py:529-575`

**Issue:** The Barkjohn 2021 formula
`PM2.5_corrected = 0.52 * PM2.5_raw - 0.085 * RH + 5.71` is implemented
twice. CLAUDE.md already documents this as a planned refactor, but it has
not been done. If one copy is updated and the other is forgotten, the live
pipeline and the training pipeline will silently produce different corrected
values for the same sensor reading.

**Why it matters:** Phase 4 RF parity depends on this. A model trained on
one formula and run against the other will produce undetectable bias on
every prediction.

**Fix:** Extract `apply_epa_correction()` into `data/corrections.py` and
import from both modules.

---

### 2. ~~Inconsistent distance metric (cosine longitude correction)~~ — **WITHDRAWN**

**Original claim:** IDW path in `engine/interpolation.py:83` skipped
`LON_CORRECTION`.

**Verification result:** The audit misread line 83 in isolation.
`engine/interpolation.py:82` applies `LON_CORRECTION` to `dlon` *before*
line 83's `sqrt`. The K-NN traffic blend at lines 195–197 and the wind
bearing at lines 251–253 do the same. All three distance computations in
`interpolation.py` use the corrected metric, matching `adjustments.py:48-49`
and `:99`. The cosine-corrected-distance invariant holds project-wide.

**Status:** No bug. Withdrawn.

---

### 3. ~~Timezone-naive risk in training pipeline~~ — **DOWNGRADED to nit**

**Original claim:** Timestamps could silently be stripped of tz, producing
wrong `local_hour_of_day` values.

**Verification result:** Both timestamp sources in
`collect_training_data.py` are constructed UTC-aware
(`pd.to_datetime(..., utc=True)` at line 326, `dt.tz_localize("UTC")` at
line 624). `requirements.txt` pins `pandas>=2.0.0`, on which `.dt.floor("h")`
preserves tz on a tz-aware Series. The downstream `dt.tz_convert("America/Chicago")`
at line 661 would raise loudly on any naive input — it cannot silently
produce wrong hours.

**Status:** No realistic silent-corruption path. A defensive
`assert df["timestamp"].dt.tz is not None` before line 695 is fine but not
required. Downgraded to a nit.

---

## High

### 4. POSIX-only file locking on snapshot writer
**File:** `data/ingestion/history.py:115-120`

**Issue:** Uses `fcntl.flock()` — POSIX-only and advisory. On Windows it
will raise `AttributeError`; on POSIX, two processes that both forget the
lock can still corrupt the CSV. `app.py` (Streamlit) and
`scripts/collector.py` can run concurrently and both write to
`data/dashboard_snapshots.csv`.

**Fix:** Use the `filelock` package (cross-platform, mandatory) or migrate
the snapshot store to SQLite append.

---

### 5. `dist_to_highway_m` missing from live feature pipeline
**Files:**
- `engine/features.py:3-8` (TODO comment)
- `data/spatial/spatial_features.py` (function exists)

**Issue:** Training data has `dist_to_highway_m` (computed in
`collect_training_data.py:362-364`). The live pipeline does not compute it
for grid cells, so Phase 4 RF inference would fail or produce wrong
predictions due to a missing feature column.

**Why it matters:** This is a hard blocker for Phase 4. Must be fixed
before flipping RF on.

**Fix:** Add `dist_to_highway_m` computation to `engine/features.py` (or a
new wrapper used by the inference path) before Phase 4 begins.

---

### 6. `ml/predictor.py` is staged for Phase 4 but not yet wired into the live pipeline — **REWRITTEN**

**Original claim:** Loads a ~200 MB pkl on import; not imported anywhere.
**Both halves were wrong on inspection.**

**Actual status:**
- `joblib.load(MODEL_PATH)` is inside `load_model()`
  (`ml/predictor.py:60`), not at module scope. There is no import-time
  hazard.
- Two callers exist: `ml/research/phase4_parity_check.py:27` and
  `ml/research/phase4_smoketest.py:22`. Not orphaned.
- `ml/models/` is empty — `rf_phase4.pkl` does not exist on disk yet.
  `load_model()` would raise `FileNotFoundError` if invoked today.
- Live request paths (`api/`, `app.py`, `engine/`) do not import it.

**Why this still matters (lower severity):** the file is plumbed for Phase
4 inference but the artifact is not built and the live path is not wired
up. CLAUDE.md correctly calls out Phase 4 as "not started."

**Fix:** No action needed today. When Phase 4 starts: build the pkl via
`ml/research/train_phase4_rf.py`, then wire `predict_grid()` into the
live request path behind a feature flag.

---

### 7. Schema drift: `hour_of_day` vs. `local_hour_of_day`
**Files:**
- `data/ingestion/history.py:44` — uses `hour_of_day`
- `ml/training/collect_training_data.py:755-756` — uses `local_hour_of_day`

**Issue:** Live snapshot column name was not updated when the training
script standardized on `local_hour_of_day`. Concatenating live snapshots
with the training set will misalign columns.

**Fix:** Rename the live snapshot column to `local_hour_of_day`.

---

### 8. OpenAQ timestamp parsing breaks on naive timestamps — **SCOPE CORRECTED (per-location)**

**File:** `data/ingestion/openaq.py:101-102`

**Issue:** Code only normalizes the `Z` suffix. Any timestamp without any
timezone marker is parsed as naive, and the subsequent
`datetime.now(timezone.utc) - reading_dt` raises `TypeError`.

**Original claim of "drops the entire fetch" was overstated.** Verification
shows the parse is wrapped in a per-location `try/except Exception` at
`data/ingestion/openaq.py:177-182`, which increments `skip_reasons["fetch_error"]`
and continues to the next location. So the blast radius is **one dropped
reading per offending location**, not the whole OpenAQ fetch.

**Why it still matters:** OpenAQ v3 nests datetime as `{"utc": "..."}` on
some endpoints — fields named `utc` are presumably UTC but carry no marker
when extracted, so the naive-input case can fire silently.

**Fix:**
```python
if reading_dt.tzinfo is None:
    reading_dt = reading_dt.replace(tzinfo=timezone.utc)
```

---

### 9. PurpleAir retry ignores `Retry-After` header
**File:** `ml/training/collect_training_data.py:188-218`

**Issue:** Fixed exponential backoff on 429s. PurpleAir often returns a
`Retry-After` header that should be honored to avoid long stalls.

**Fix:** Parse `Retry-After` and use it when present; fall back to
exponential.

---

### 10. ~~Humidity column can be silently lost~~ — **WITHDRAWN**

**Original claim:** `apply_epa_correction()` could drop `humidity` and the
keep-list NaN-fill wouldn't restore it.

**Verification result:** `apply_epa_correction()` never drops `humidity`
— `out = df.copy()` at line 57 preserves all columns, and no subsequent
operation removes one. Independently, the post-keep fallback at
`purpleair.py:156-157` writes `df["humidity"] = float("nan")` whenever the
column is absent, so the absent-column case is already handled. Both
paths produce a `humidity` column in the final DataFrame.

**Status:** No bug. Withdrawn.

---

## Medium

### 11. ~~Cell-index rounding at boundaries~~ — **WITHDRAWN**

**Original claim:** `int()` truncation plus `>=` at `api/routes/cells.py:52-60`
misplaces exact-boundary points.

**Verification result:** Lines 54 and 56 of `api/routes/cells.py` use
`lat >= BBOX["north"]` and `lon >= BBOX["east"]` to **reject** exact-boundary
points before any `int()` call. This makes the bbox half-open on north/east
exactly as the docstring says. For interior points the dividend is strictly
in `[0, _GRID_SIZE)`, so `int()` truncation matches `np.floor` behaviour.
The second cited location (`engine/interpolation.py:188-191`) does not
contain any cell-indexing code — those lines extract traffic columns. The
grid is built via `np.linspace` + `meshgrid`, never per-point indexed.

**Status:** No bug. Withdrawn.

---

### 12. Confidence can NaN-out silently in empty regions
**File:** `engine/interpolation.py:126-132`

**Issue:** NaNs are clipped to [0, 1] so they vanish, but truly empty
sub-regions then report confident readings.

**Fix:** Detect and explicitly mark cells with no neighbors within the
search radius as low/zero confidence with a logged warning.

---

### 13. Meteostat missing → silent synthetic-wind fallback
**File:** `ml/training/collect_training_data.py:606-612`

**Issue:** If `meteostat` isn't installed, the training script logs a
warning and proceeds with climate normals for wind. Easy to miss; produces
a weaker model.

**Fix:** Hard-fail unless `--allow-synthetic-wind` is passed explicitly.

---

### 14. TomTom `_congestion_score` swallows zero free-flow
**File:** `data/ingestion/traffic.py:26-34`

**Issue:** Returns 0.0 for `free_flow_speed <= 0` without logging. Zero
free-flow indicates bad API data, not real traffic.

**Fix:** Log a warning when this branch fires; track frequency.

---

### 15. API and Streamlit caches desynchronized
**Files:**
- `api/routes/grid.py:23` (300 s)
- `app.py:52-66` (300 s)

**Issue:** Independent caches with the same TTL drift apart over time;
the Streamlit dashboard and the new AERIA frontend can show different
heatmaps simultaneously.

**Fix:** Document the 5-minute window, or share a cache layer between the
two front-ends.

---

### 16. `COLUMNS` constant drifts from `build_features()`
**File:** `data/ingestion/history.py:27-46`

**Issue:** Hand-maintained column list. Adding a new feature to
`build_features()` silently drops it from the snapshot CSV.

**Fix:** Derive `COLUMNS = list(new_rows.columns)` from the actual
DataFrame.

---

## Low / Nits

### 17. Two libraries handle zip lookups
**Files:** `viz/heatmap.py:19-25` (uszipcode) vs. `api/routes/cells.py:22-23` (pgeocode + uszipcode)

Different libraries can return different zips for the same point.
Standardize on one.

### 18. `lru_cache` outlives the 30-day OSMnx TTL
**File:** `data/spatial/spatial_features.py:104`

`compute_distance_to_highway` is `lru_cache`d but the underlying network
data refreshes every 30 days. Cache survives the refresh and returns
stale distances.

**Fix:** Tie cache lifetime to the OSMnx refresh, or clear it explicitly
on refresh.

### 19. DFW airport coords hardcoded in two places
**Files:** `ml/predictor.py:33-34`, `ml/training/collect_training_data.py:72-73`

`(32.8998, -97.0403)` hardcoded twice. Move to `config.py`.

### 20. Misc cleanup
- `_zip_lookup` 404 doesn't distinguish "not found" vs. "service down"
  (`api/routes/cells.py:26-32`).
- Inconsistent log levels across ingestion modules (`debug` vs. `warning`
  for similar events).

---

## Issue Count by Severity (post-verification)

| Severity     | Original | Withdrawn / Downgraded | Net |
|--------------|----------|------------------------|-----|
| Critical     | 3        | #2 withdrawn, #3 → nit | 1   |
| High         | 7        | #6 rewritten (still listed at lower priority), #10 withdrawn | 6 (1 reframed) |
| Medium       | 6        | #11 withdrawn          | 5   |
| Low/Nit      | 4        | +#3 (downgraded)       | 5   |
| **Total**    | **20**   | 4 withdrawn            | **16 active** |

Verified items not listed above (#8) remain real but with corrected scope.
Items not in {#2, #3, #6, #8, #10, #11} were not re-verified.

---

## Phase 4 Readiness Assessment (revised)

The codebase is closer to Phase 4 ready than the original audit suggested.
The hard blockers are:

- **#1** — EPA formula must be extracted to a shared module so live and
  training pipelines stay in lockstep.
- **#5** — `dist_to_highway_m` must exist in the live feature pipeline,
  not just training, or RF inference will crash on a missing column.

Issue #2 (distance metric) is **not** a blocker — verification confirmed
the cosine correction is applied consistently. Issue #3 (timezone) is not
a realistic risk on pandas 2.x.

Other items worth resolving before Phase 4 (lower priority):
- **#7** — schema drift between live snapshots and training set.
- **#8** — OpenAQ naive-timestamp robustness (per-location only).
- **#9** — honor `Retry-After` in PurpleAir retries.
- **#13** — make synthetic-wind fallback opt-in.
