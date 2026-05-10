# DFW Air Quality — Project State Snapshot

**Generated:** 2026-05-08 11:29 CDT
**Purpose:** Hand this to Claude at the start of any future session. It complements [CLAUDE.md](CLAUDE.md) (rules) and [README.md](README.md) (project overview) with a *current-state* briefing — what's done, what's pending, what's deprecated, and what to read next.
**Staleness:** This file is a snapshot. Regenerate it after any structural change or when more than ~5 commits old. Verify file paths and route signatures before acting on the details below.

---

## TL;DR

- Phases 1–3 are done; Phase 4 (Random Forest) was shelved as a negative result — IDW + post-IDW traffic/wind adjustments is the production model.
- Phase 6 (AERIA UI) is live and functional: city + street 3D views, persistent left panel, zip search, status bar.
- Phase 5 (Route Lab) is **partially done**: items 1–4 (router engine, `POST /api/route`, Route Lab tab, caching + Brotli) shipped in commits `65f4ffe`, `3bd17c2`, `c524743`, and the in-flight item-4 PR. Items 5–9 (loading page, frontend perf, deploy, domain, E2E smoke) remain.
- Estimated remaining work before shipping is ~10–17 hrs across items 5–9.
- Legacy Streamlit (`app.py`, `viz/heatmap.py`) is still running in parallel and **must not be modified**.

---

## Locked rules (re-stated from CLAUDE.md)

> If [CLAUDE.md](CLAUDE.md) is uploaded alongside this doc, prefer it — it's authoritative and more complete. This is the load-bearing subset so this file works standalone.

**Don't touch:**
- [app.py](app.py), [viz/heatmap.py](viz/heatmap.py) — legacy Streamlit, must keep running
- The `pm25` column is **already EPA-corrected** at ingest in [data/ingestion/purpleair.py](data/ingestion/purpleair.py). Never apply the Barkjohn correction again downstream. The raw value lives in `pm25_raw`. OpenAQ data is not corrected (reference-grade monitors are pre-calibrated).
- **CF=1 channel constraint:** both pipelines must read `pm2.5_cf_1_*` fields, never ATM. The Barkjohn 2021 formula was derived on CF=1 data — substituting ATM produces a biased correction.
- Phase 4 RF training-set columns vs. [engine/features.py](engine/features.py) live-only columns are **not interchangeable**. The live columns can't be reconstructed historically without paid TomTom Traffic Stats.

**Pipeline conventions:**
- Sensor readings (PurpleAir, OpenAQ) are **never** traffic/wind-adjusted — they already reflect real-world conditions at their physical locations. Adjustments are post-IDW grid math only ([engine/interpolation.py](engine/interpolation.py)).
- OpenAQ failure is non-fatal: `fetch_openaq()` returns an empty DataFrame; pipeline continues on PurpleAir alone. The `source` column ("purpleair" / "openaq") preserves provenance through the concat.
- All distance math multiplies longitude deltas by `cos(32.78°) ≈ 0.840` (`config.LON_CORRECTION`) to correct ~19% east-west distortion at Dallas latitude.
- Grid cells use IDW-weighted blend of the 5 nearest TomTom traffic points, not snap-to-nearest, to avoid Voronoi artifacts.
- Live snapshots ([data/dashboard_snapshots.csv](data/dashboard_snapshots.csv)) and Phase 4 training set (`ml/data/history.csv`) are intentionally separate files — a training rebuild must not corrupt accumulated dashboard state.

**Process rules:**
- Python 3.10+ required.
- Do not refactor previous-phase code unless the user asks.
- Update [requirements.txt](requirements.txt) when adding any new library.
- Developer is intermediate level — explicit over clever, small functions, no heavy docstrings.

---

## Phase status

| Phase | Status | Notes |
|---|---|---|
| 1 — Scaffold + PurpleAir ingest | ✅ Done | |
| 2 — IDW + Folium heatmap | ✅ Done | |
| 3 — Traffic + wind fusion | ✅ Done | Exponential traffic curve, per-cell wind direction factor |
| 4 — Random Forest | ❌ Shelved | See [ml/docs/PHASE4_RESULT.md](ml/docs/PHASE4_RESULT.md). `ml/predictor.py` and `ml/training/collect_training_data.py` are marked DEPRECATED; `ml/models/` is empty. |
| 5 — Route Lab | 🟡 Partial | Items 1–4 done (router engine, `POST /api/route`, Route Lab tab, caching + Brotli); items 5–9 (loading page, frontend perf, deploy, domain, E2E smoke) pending |
| 6 — AERIA UI | 🟢 Active | City + street views functional; Route Lab tab now enabled (commit `c524743`); Time Machine remains placeholder-disabled in [TopNav.tsx](web/src/components/ui/chrome/TopNav.tsx) |

---

## Repo map (annotated, current)

```
dfw-airquality/
├── app.py                       # Streamlit (LEGACY, do not modify)
├── config.py                    # BBOX, GRID_RESOLUTION, IDW_POWER, TRAFFIC_*, AQI_*, etc.
├── CLAUDE.md                    # Rules + decisions (read first)
├── README.md                    # Project overview
├── ALGORITHMS.md                # Math deep-dive
├── UI_SUMMARY.md                # AERIA UI summary
├── PROJECT_STATE.md             # ← this file
├── requirements.txt
├── .env                         # API keys (gitignored)
│
├── api/                         # FastAPI — thin wrapper over engine/ + data/
│   ├── main.py                  # App init, CORS (GET+POST), Brotli middleware, always-on grid warmup thread, opt-in `AERIA_PRELOAD_GRAPH=1` walking-graph preload
│   ├── routes/
│   │   ├── health.py            # /api/health
│   │   ├── sensors.py           # /api/sensors      (5 min TTL)
│   │   ├── grid.py              # /api/grid         (30 min TTL; first call 5–15s)
│   │   ├── cells.py             # /api/cells/{zip_code}, /api/cells/at  (rides grid TTL)
│   │   ├── route.py             # POST /api/route   (10 min route LRU + grid-snapshot validation)
│   │   └── geocode.py           # /api/geocode/suggest  (10 min, 10k-entry typeahead cache)
│   └── schemas/responses.py     # Pydantic: SensorReading, SensorsResponse, GridResponse, CellResponse, CellAtResponse, RouteResponse, RouteStats, GeoJSONLineString, BBox
│
├── engine/
│   ├── adjustments.py           # traffic_factor, wind_dispersal_factor, wind_direction_factor (+ vectorized)
│   ├── interpolation.py         # run_idw, adjust_grid
│   ├── features.py              # build_features (per-sensor live columns)
│   └── router.py                # LocationIQ geocoding (LRU) + OSM walking graph (disk-persisted) + dual Dijkstra (shortest / cleanest); `find_routes`, `preload_graph`, CLI
│
├── data/
│   ├── ingestion/
│   │   ├── purpleair.py         # fetch_sensors (EPA-corrected at ingest), classify_pm25
│   │   ├── openaq.py            # fetch_openaq (v3, reference monitors)
│   │   ├── weather.py           # fetch_wind (OpenWeatherMap)
│   │   ├── traffic.py           # fetch_traffic (TomTom 5×5)
│   │   ├── history.py           # save_snapshot → data/dashboard_snapshots.csv
│   │   └── osm.py               # ⚠ EMPTY (placeholder)
│   ├── spatial/spatial_features.py  # OSMnx highway distance, LRU + 30-day disk cache
│   ├── dashboard_snapshots.csv  # Live snapshot accumulator
│   └── .cache/                  # OSMnx + requests-cache
│
├── ml/                          # Phase 4 artifacts (shelved)
│   ├── predictor.py             # ⚠ DEPRECATED — RF inference (model files not present)
│   ├── training/
│   │   └── collect_training_data.py  # ⚠ DEPRECATED — historical builder
│   ├── analysis/                # Coverage + audit scripts
│   ├── research/                # Phase 4 negative-result audit trail
│   ├── models/                  # ⚠ EMPTY (no .pkl files)
│   ├── data/                    # history.csv, quality_report.json (gitignored)
│   └── docs/                    # PHASE4_RESULT.md, PHASE4_HANDOFF.md, DFW_Algorithm_Report.md, COLLECT_TRAINING_DATA_HISTORY.md
│
├── web/                         # Vite + React + TypeScript + R3F (AERIA)
│   └── src/  (see Frontend snapshot below)
│
├── design/
│   ├── DESIGN_NOTES.md          # SOURCE OF TRUTH for UI design intent
│   ├── mocks/                   # Static mockups
│   └── screens/                 # Screen references
│
├── scripts/
│   └── collector.py             # Headless live snapshot collector (cron/background)
│
├── viz/
│   └── heatmap.py               # Legacy Folium overlay (paired with app.py)
│
└── tests/
    ├── conftest.py
    ├── test_adjustments.py
    ├── test_epa_correction.py
    ├── test_geocode_endpoint.py
    ├── test_history_snapshot.py
    ├── test_interpolation.py
    ├── test_interpolation_confidence.py
    ├── test_openaq_parsing.py
    ├── test_route_endpoint.py
    ├── test_router.py
    ├── test_spatial_cache.py
    ├── test_traffic_scoring.py
    ├── test_zip_lookup.py
    └── test_zip_lookup_errors.py
```

**Working tree:** `AUDIT_REPORT.md` and `CHANGES.md` are fully gone — neither tracked in git nor present on disk. Earlier versions of this doc described them as "removed but unstaged"; that's resolved.

---

## Backend snapshot

**[engine/](engine/)**
- [interpolation.py](engine/interpolation.py): `run_idw()`, `adjust_grid()` — IDW interpolation + post-IDW traffic/wind adjustments (cosine-corrected longitude deltas).
- [adjustments.py](engine/adjustments.py): `traffic_factor`, `nearest_traffic_point`, `wind_dispersal_factor`, `wind_direction_factor` — scalar + vectorized variants used by both interpolation and per-sensor features.
- [features.py](engine/features.py): `build_features()` — per-sensor live columns for `dashboard_snapshots.csv`. **Live-only**; columns here are NOT fed to any RF model.
- [router.py](engine/router.py): full Phase 5 implementation (commit `65f4ffe`). LocationIQ geocoding (LRU 10k entries) → OSM walking-graph load (disk-persisted) → edge annotation with PM2.5 sampled at midpoints → dual Dijkstra (length-only "shortest" + PM-weighted "cleanest"). Public surface: `find_routes(start, end, grid=None) -> RouteComparison`, `preload_graph()`, plus a CLI with mock-PM mode for offline smoke. Errors: `GeocodeFailure`, `OutOfDFWError`, `DisconnectedRouteError`.

**[data/ingestion/](data/ingestion/)** — all live, all return DataFrames; OpenAQ failure is non-fatal (returns empty).

**[data/spatial/spatial_features.py](data/spatial/spatial_features.py)** — `compute_distance_to_highway()` with LRU + 30-day disk cache. Works at training time (per sensor) and inference time (per grid cell).

**[config.py](config.py)** — `LAT_CENTER`, `LON_CORRECTION`, `BBOX`, `MAP_CENTER`, `MAP_ZOOM`, `DFW_AIRPORT_LAT_LON`, `REFRESH_INTERVAL_SECONDS`, `AQI_THRESHOLDS`, `AQI_COLORS`, `PURPLEAIR_BASE_URL`, `GRID_RESOLUTION` (= 200), `IDW_POWER`, `IDW_SEARCH_RADIUS_DEG`, `TRAFFIC_WEIGHT`, `TRAFFIC_DECAY_RADIUS_M`, `SENSOR_HW_PROXIMITY_M`. (`OPENAQ_API_KEY` is also defined here but it's an `os.getenv` env-var pull, not a constant.)

**[app.py](app.py)** — Streamlit entry, ~138 lines: sidebar + metrics row + Folium map. Cached loaders at 5 min TTL. **Do not modify** while Phase 6 is active.

---

## API snapshot ([api/](api/))

| Route | Returns | Cache |
|---|---|---|
| `GET /api/health` | Liveness + cache-warm status | — |
| `GET /api/sensors` | PurpleAir + OpenAQ combined, EPA-corrected | 5 min (own cache) |
| `GET /api/grid` | Full IDW + adjusted PM2.5 grid (200×200, per `config.GRID_RESOLUTION`) | 30 min (first call 5–15s) |
| `GET /api/cells/{zip_code}` | Cell PM2.5 by 5-digit zip | rides 30-min grid TTL |
| `GET /api/cells/at?lat=&lon=` | Cell PM2.5 by reverse geocode | rides 30-min grid TTL |
| `POST /api/route` | Cleanest vs. shortest walking route between two DFW addresses | 10 min route LRU (1k entries) keyed on `(start, end)`, validated against current grid snapshot timestamp |
| `GET /api/geocode/suggest` | LocationIQ typeahead suggestions for the Route Lab inputs | 10 min, 10k entries |

All routes registered with `prefix="/api"` in [api/main.py](api/main.py). Imports `engine/`, `data/ingestion/`, `config.BBOX` directly. **No logic duplicated** — strictly a JSON wrapper.

**CORS allows GET + POST** ([api/main.py:68](api/main.py#L68): `allow_methods=["GET", "POST"]`, widened in commit `3bd17c2`). Allowed origins come from always-on dev defaults (`localhost:5173`, `127.0.0.1:5173`) + the comma-separated `AERIA_CORS_ORIGINS` env var (**not** `CORS_ORIGINS` — the PDF is wrong on this name).

**Compression:** Brotli middleware ([api/main.py:76-80](api/main.py#L76-L80)) with `quality=4` and `minimum_size=500`. Registered after `CORSMiddleware` so it sits outermost on the response path. Falls back to identity for clients without `Accept-Encoding: br`.

**Warmup:** `_start_warmup` ([api/main.py:118-124](api/main.py#L118-L124)) runs unconditionally on every startup in a daemon thread, priming the grid cache so `/api/health` reports `cache_warm=true` within ~5–15 s. Eliminates the prior cold-boot deadlock where the frontend gated on `cache_warm`. The opt-in `AERIA_PRELOAD_GRAPH=1` env var ([api/main.py:127-137](api/main.py#L127-L137)) additionally pre-loads the OSM walking graph, so the first `/api/route` call doesn't pay the 60–180 s graph-load cost.

**Grid sizes — three different numbers, don't confuse them:**
- **200×200** — backing IDW grid the API returns (`config.GRID_RESOLUTION`)
- **30×30** — clickable cells the city scene renders (UI samples down from the 200×200)
- **60×60** — *planned* downsized grid response in the Phase 5 perf work (not current)

**Other API artifacts:** [api/README.md](api/README.md), [api/openapi.snapshot.json](api/openapi.snapshot.json) (committed OpenAPI spec — read before changing route signatures), [api/scripts/snapshot_openapi.py](api/scripts/snapshot_openapi.py) (regenerates the snapshot; diff across commits to catch unintended contract changes).

---

## Frontend snapshot ([web/](web/))

**Stack:** Vite 5.4 + React 18.3 + TypeScript 5.4 + React Three Fiber 8.18 + @react-three/drei 9.122 (three 0.160) + Zustand 4.5 + Tailwind 3.4 + simplex-noise 4.0. No external UI lib; chrome is hand-built.

**Entry:** [src/App.tsx](web/src/App.tsx) — health polling, grid+sensor fetches, view transitions, dev access.

**Views:**
- **City** — [CityScene.tsx](web/src/components/scene/city/CityScene.tsx): isometric 3D, instanced grey buildings, 30×30 clickable cells, AQI-tinted floor, particle field encoding AQI by color + density.
- **Street** — [StreetScene.tsx](web/src/components/scene/street/StreetScene.tsx): first-person dusk view, particles surround viewer driven by selected cell PM2.5; ESC returns to city.

**Stores ([src/state/](web/src/state/)):** `view`, `grid`, `scene`, `connection`, `sensors`.

**Chrome ([src/components/ui/](web/src/components/ui/)):**
- `chrome/` — [TopNav.tsx](web/src/components/ui/chrome/TopNav.tsx) (4 tabs: city + street enabled, time + route disabled — note: web/CONTRACT.md says "three disabled" but is stale, post-dates `87d7876 street view`), [TopStatusBar.tsx](web/src/components/ui/chrome/TopStatusBar.tsx) (sensor count, metro PM2.5, UPDATED timestamp — **wind metric is hidden**, /api/sensors doesn't expose wind at metro level yet), [BreadcrumbFooter.tsx](web/src/components/ui/chrome/BreadcrumbFooter.tsx) (full-width bottom: nav path + build metadata)
- `panels/` — [LeftPanel.tsx](web/src/components/ui/panels/LeftPanel.tsx) (280px persistent), [CellInfoCard.tsx](web/src/components/ui/panels/CellInfoCard.tsx) (top-right, city only), [ZipSearch.tsx](web/src/components/ui/panels/ZipSearch.tsx)
- `overlays/` — [FadeOverlay.tsx](web/src/components/ui/overlays/FadeOverlay.tsx) (300ms cross-fade between views), [StreetEmptyState.tsx](web/src/components/ui/overlays/StreetEmptyState.tsx)
- root — [HealthBadge.tsx](web/src/components/ui/HealthBadge.tsx) (bottom-left pulse)

**World helpers ([src/world/](web/src/world/)):** `bbox.ts` (grid math + lat/lon ↔ cell), `aqi.ts` (EPA breakpoints + colors), `healthGuidance.ts`, building generators, simplex noise.

**API client:** [src/api/client.ts](web/src/api/client.ts) — `getHealth`, `getGrid`, `getCellByZip`, `getCellAt`, `getSensors`. Reads `VITE_API_BASE_URL` (with `localhost:8000` fallback).

**Frontend contract docs to read before backend ↔ web work:** [web/README.md](web/README.md), [web/CONTRACT.md](web/CONTRACT.md) (frontend↔backend boundary contract), [web/docs/](web/docs/), [web/.env.example](web/.env.example).

---

## Design language (compressed from [DESIGN_NOTES.md](design/DESIGN_NOTES.md))

1. **Three views shipped**: city (isometric) ↔ street (first-person) ↔ Route Lab. Time Machine remains a disabled placeholder for future work.
2. **Signal hierarchy**: particles are the *primary* AQI cue (color + density); cell floor tint is *secondary* (faint); exact PM2.5 only on interaction.
3. **Aesthetic**: dark, atmospheric, dusk-toned. Grey concrete buildings (not chrome). Gold `#ffd166` for live state and selection only. Hairline borders, no emoji, no rainbow.
4. **Typography**: Inter Tight (body) / JetBrains Mono (metadata) / Fraunces serif (large readings).
5. **Grid**: 30×30 cells over Dallas bbox (lat 32.55–33.08, lon -97.05 to -96.46), ~1 mile per cell. Zip codes are the primary cell ID via reverse geocoding.

**[DESIGN_NOTES.md](design/DESIGN_NOTES.md) is the source of truth — read it before any UI change.**

---

## What's left — Phase 5 + Deploy (ordered by dependency)

> *Source: distilled from the user's Phase 5 plan PDF — this is **planning intent**, not verified contracts. Confirm exact env var names, route signatures, and library choices against the live code before acting.*

| # | Item | Est. |
|---|---|---|
| 1 | ✅ **DONE (commit `65f4ffe`)** — `engine/router.py` shipped: LocationIQ geocoding (LRU 10k), OSM walking graph (disk-persisted), edge PM2.5 annotation at midpoints, dual Dijkstra (shortest + cleanest), GeoJSON LineString output with `distance_m` / `mean_pm25` / `walk_seconds` / `total_exposure`, CLI with mock-PM mode. Public surface as planned: `find_routes(start, end, grid=None) -> RouteComparison` and `preload_graph()`. | 2–3 hr |
| 2 | ✅ **DONE (commit `3bd17c2`)** — `POST /api/route` with Pydantic in/out, error mapping for geocode/out-of-DFW/disconnected, CORS widened to `["GET", "POST"]`. | 1–1.5 hr |
| 3 | ✅ **DONE (commit `c524743`)** — Route Lab tab in [TopNav.tsx](web/src/components/ui/chrome/TopNav.tsx) (`enabled: true`); `RouteLabPanel.tsx` provides the two address inputs + find-route flow. | 3–4 hr |
| 4 | ✅ **DONE (in-flight item-4 PR)** — Pipeline cache `_TTL_SECONDS` 300→1800; `SAMPLE_GRID` 8→5 (1,200 TomTom calls/day cap); endpoint-layer route cache (`TTLCache(1000, ttl=600)`) keyed on normalized `(start, end)` with grid-snapshot timestamp validation; `BrotliMiddleware(quality=4, minimum_size=500)` after CORS. The PDF's per-source caches (wind/traffic 10-min) intentionally collapsed into the single 30-min pipeline TTL — wind and traffic only refresh inside `_run_full_pipeline` anyway. *(The PDF mentions a 60×60 grid here — that's a planned downsize from the current 200×200, not today's state.)* | 1–1.5 hr |
| 5 | **Loading page** — dusk gradient backdrop, gold AERIA wordmark reveal, rolling status text ("Loading 27 sensors / Building grid / Reading traffic") while React boots. Page pings `/api/health` on load to wake Render's free dyno. | 2–3 hr |
| 6 | **Frontend perf** — `React.lazy` + Suspense to lazy-load the R3F city scene; code-split the Route Lab tab; verify with `vite-bundle-visualizer`. | 1–2 hr |
| 7 | **Deploy** — Vercel for frontend (`VITE_MAPBOX_TOKEN`, `VITE_API_BASE_URL` — Vite only exposes `VITE_`-prefixed vars to the browser; the PDF's `MAPBOX_TOKEN` / `VITE_API_BASE` are wrong); Render free tier for backend (write a new `render.yaml` — doesn't exist yet, plus `MAPBOX_TOKEN` and `AERIA_CORS_ORIGINS` — *not* `CORS_ORIGINS` as the PDF says, see [api/main.py:40](api/main.py#L40)); cron-job.org pinger every 10 min on `/api/health`. | 2–3 hr |
| 8 | **Domain + DNS** — Cloudflare/Namecheap/Porkbun; apex + www CNAME → Vercel; `api.` CNAME → Render; Let's Encrypt SSL auto-provision. Do this earlier in the day, propagation can take hours. | 30–60 min + wait |
| 9 | **E2E smoke + buffer** — full user flow on live URLs; 3–4 real DFW address pairs (include same-zip + cross-metro); mobile breakpoint; copy review; fix what breaks. | 2–4 hr |

**Total: 15–23 hr active, budget 20–26 hr across the week.**

---

## How to run it

Requires **Python 3.10+** and Node 18+ (for the Vite dev server).

```bash
# Backend (FastAPI, port 8000)
source venv/bin/activate          # python -m venv venv if not yet created
uvicorn api.main:app --reload --port 8000

# Frontend (Vite dev server, port 5173)
# `--legacy-peer-deps` is required: R3F v8 has non-optional peer deps on
# react-native/expo that otherwise pull React 19 and break the React 18.3 install.
cd web && npm install --legacy-peer-deps && npm run dev

# Legacy Streamlit (port 8501) — runs in parallel, do not modify
streamlit run app.py

# Background snapshot collector
python scripts/collector.py                # 30-min interval (default)
python scripts/collector.py --interval 15

# Tests
pytest

# Live tree check (verify before trusting this doc)
git log --oneline -10
git status
```

Required `.env` keys at the repo root: `PURPLEAIR_API_KEY`, `OPENAQ_API_KEY`, `OPENWEATHERMAP_API_KEY`, `TOMTOM_API_KEY`. The frontend additionally reads `VITE_API_BASE_URL` (and, for Phase 5, will need `VITE_MAPBOX_TOKEN`) — see [web/.env.example](web/.env.example).

---

## Known issues / production bugs (from [web/CONTRACT.md](web/CONTRACT.md) "Future cleanup")

- **✅ RESOLVED (2026-05-09, commit `3bd17c2`) — Cold-boot chicken-and-egg:** [api/routes/health.py](api/routes/health.py) reports `cache_warm` based on whether `/api/grid` has populated its cache. The frontend's connection store gates `/api/grid` fetch on `cache_warm === true`. Previously, on cold boot the page hung forever in `'warming'` until something hit `/api/grid` directly. Fix: `_start_warmup` ([api/main.py:118-124](api/main.py#L118-L124)) now runs unconditionally on every startup in a daemon thread, priming the grid cache so `cache_warm` flips true within 5–15 s without operator intervention.
- **🟡 MITIGATED (2026-05-09, in-flight item-4 PR) — `/api/grid` cache instability under load:** Previously observed responding in 116ms then 40s in the same session — cache evicted mid-session, the page silently empties (cells go to zero, particles disappear) until hard refresh. The 30-min TTL bump (300s → 1800s) reduces refresh frequency 6×, so eviction storms are far less likely. **The underlying race remains:** at every TTL boundary, two simultaneous misses can both trigger `_run_full_pipeline` concurrently — wasted compute, not a correctness bug, but the bug class hasn't been eliminated, just rate-limited. Real fix: backend self-warm on a TTL-aware schedule (refresh in background before the cache window closes).
- **✅ RESOLVED (2026-05-09, commit `c524743`) — Phase 6 route placeholder shipped:** "Find a route · Cleanest path · Soon" CTA replaced by a real `RouteLabPanel.tsx` ([web/src/components/ui/panels/RouteLabPanel.tsx](web/src/components/ui/panels/RouteLabPanel.tsx)). The Pin button on `CellInfoCard` and "Drop into street" button placeholders may persist (not re-verified in this audit).
- **No URL deep-linking** (view routing is in-memory only — no shareable links to a cell or street view).
- **City camera state is in-memory only** (survives view round-trips, lost on reload).
- **`prefers-reduced-motion` not honored** for FadeOverlay or particle drift.
- **Top chrome row not responsive below 1500px** — at 1366×768 nav, status bar, and zip search overlap. Desktop-first v1.
- **Route cache duplicate-compute race on simultaneous misses** — `cachetools.TTLCache` is thread-safe per-operation but the check-then-write sequence in [api/routes/route.py:64-97](api/routes/route.py#L64-L97) is not. Two concurrent first-time requests for the same `(start, end)` will both run `find_routes` and both write. Accepted at portfolio scale; revisit if traffic shows redundant compute spikes.

## Open cleanup items

Each item is flagged with whether it's in scope for the Phase 5 sprint. **A fresh Claude session should not pull on out-of-scope items mid-task** — they're tracked here for awareness, not as work to do.

- **✅ DONE (2026-05-09):** `AUDIT_REPORT.md` and `CHANGES.md` are fully gone from working tree and git index. Earlier versions of this section flagged them as "removed but unstaged" — that's no longer true.
- **⛔ Out of scope:** [ml/predictor.py](ml/predictor.py) and [ml/training/collect_training_data.py](ml/training/collect_training_data.py) are marked DEPRECATED but **stay untouched during Phase 5**. Phase 4 was a negative result; deleting these is a separate decision the user makes after ship. Do not "tidy them up" mid-route-lab task.
- **⛔ Out of scope:** Empty [data/ingestion/osm.py](data/ingestion/osm.py) — leave it alone; deleting it is not Phase 5 work even though it's trivial.
- **⛔ Out of scope:** Extracting `apply_epa_correction()` into a shared `data/corrections.py` module. Planned refactor noted in [CLAUDE.md](CLAUDE.md) — **do not start this during Phase 5**. The duplication is intentional pending an explicit user ask.

---

## Session-start checklist for Claude

1. Read [CLAUDE.md](CLAUDE.md) (rules + locked decisions), then this file (current state).
2. Then read the doc relevant to the task:
   - UI work → [design/DESIGN_NOTES.md](design/DESIGN_NOTES.md)
   - Algorithm/math work → [ALGORITHMS.md](ALGORITHMS.md)
   - Phase 4 history (only if asked) → [ml/docs/PHASE4_RESULT.md](ml/docs/PHASE4_RESULT.md)
3. Confirm which phase the user is working on before editing anything.
4. **Do not touch** [app.py](app.py) or [viz/heatmap.py](viz/heatmap.py) — legacy Streamlit must keep running.
5. **Do not re-apply EPA correction** anywhere downstream — `pm25` is already corrected at ingest in [data/ingestion/purpleair.py](data/ingestion/purpleair.py).
6. **Do not mix feature sets:** Phase 4 RF training columns vs. live-only `engine/features.py` columns are not interchangeable (live columns can't be reconstructed historically without paid TomTom Traffic Stats).
7. The FastAPI backend in [api/](api/) is a thin JSON wrapper — import from `engine/` and `data/`, never duplicate logic.

---

## Key references

- [CLAUDE.md](CLAUDE.md) — rules, decisions, do/don't
- [README.md](README.md) — project pitch + setup
- [ALGORITHMS.md](ALGORITHMS.md) — IDW, EPA correction, traffic/wind math
- [UI_SUMMARY.md](UI_SUMMARY.md) — AERIA UI overview
- [design/DESIGN_NOTES.md](design/DESIGN_NOTES.md) — design source of truth
- [ml/docs/PHASE4_RESULT.md](ml/docs/PHASE4_RESULT.md) — why RF was shelved
- [ml/docs/PHASE4_HANDOFF.md](ml/docs/PHASE4_HANDOFF.md)
- [ml/docs/DFW_Algorithm_Report.md](ml/docs/DFW_Algorithm_Report.md)
- [ml/docs/COLLECT_TRAINING_DATA_HISTORY.md](ml/docs/COLLECT_TRAINING_DATA_HISTORY.md)
