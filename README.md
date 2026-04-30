# DFW Air Quality Dashboard

A real-time, street-level PM₂.₅ air quality dashboard for the Dallas–Fort Worth metro area. Fuses live IoT sensor data, traffic congestion, and weather into an interpolated heatmap — with a cleanest-route optimizer for walking and biking paths.

---

## What It Does

- Pulls live PM₂.₅ readings from **27 PurpleAir sensors** across the DFW metro and supplements them with **OpenAQ** reference monitors
- Applies **EPA correction** (AirNow Fire and Smoke Map formula) to raw PurpleAir readings using humidity
- Interpolates a smooth **200×200 PM₂.₅ grid** using IDW (Inverse Distance Weighting) with cosine-corrected distance calculations for Dallas latitude
- Adjusts the interpolated grid using **live TomTom traffic congestion** (exponential curve weighting) and **OpenWeatherMap wind direction** (per-cell cosine similarity factor)
- Renders as a **Gaussian-smoothed raster overlay** on an interactive Folium map — not 40,000 DOM rectangles
- Accumulates live snapshots for drift monitoring and future ML training

---

## Architecture

```
dfw-airquality/
├── app.py                  # Streamlit entry point
├── CLAUDE.md               # This file — always read at session start
├── .env                    # API keys (gitignored — never commit this)
├── .gitignore
├── requirements.txt
├── config.py               # Constants: bounding box, grid, IDW, traffic/wind params
├── project_context.txt     # Project-wide context notes
├── data/
│   ├── ingestion/                   # Live API fetchers
│   │   ├── purpleair.py             # PurpleAir live ingestion (EPA-corrected)
│   │   ├── openaq.py                # OpenAQ v3 ingestion (secondary PM2.5 source)
│   │   ├── weather.py               # OpenWeatherMap ingestion (live wind)
│   │   ├── traffic.py               # TomTom ingestion (8×8 sample grid, live)
│   │   ├── osm.py                   # (empty) Overpass / OSM geometry — future use
│   │   └── history.py               # Live dashboard snapshot accumulator
│   ├── spatial/
│   │   └── spatial_features.py      # OSMnx highway-distance feature builder
│   ├── dashboard_snapshots.csv      # Accumulated live snapshots (live pipeline artifact)
│   └── .cache/                      # OSMnx + other cached fetches
├── engine/
│   ├── adjustments.py      # Shared traffic/wind math (scalar + vectorised)
│   ├── interpolation.py    # IDW interpolation + post-IDW grid adjustments
│   ├── features.py         # Per-sensor live feature columns (for dashboard_snapshots.csv)
│   └── router.py           # (empty) Route optimizer — Phase 5
├── ml/                              # Everything ML-related
│   ├── predictor.py                 # Phase 4 RF inference (dead code — not wired up)
│   ├── training/
│   │   └── collect_training_data.py # Canonical Phase 4 training-data builder
│   ├── research/                    # Negative-result audit trail
│   │   ├── train_phase4_rf.py
│   │   ├── train_phase4_residual_rf.py
│   │   ├── phase4_parity_check.py
│   │   ├── phase4_smoketest.py
│   │   └── review_180day_run.py
│   ├── analysis/
│   │   ├── sensor_coverage_check.py
│   │   ├── openaq_coverage_check.py
│   │   └── output/                  # Generated PNGs / CSVs
│   ├── models/                      # .pkl files (gitignored)
│   ├── data/                        # ML-specific data artifacts
│   │   ├── history.csv              # Phase 4 training set (gitignored)
│   │   ├── quality_report.json      # Quality report for the training-data run
│   │   ├── collection_log.txt       # Audit log for the training-data run
│   │   └── .checkpoints/            # Per-sensor parquet resume points
│   └── docs/                        # Phase 4 + algorithm documentation
│       ├── PHASE4_HANDOFF.md
│       ├── PHASE4_RESULT.md
│       ├── DFW_Algorithm_Report.md
│       └── COLLECT_TRAINING_DATA_HISTORY.md
├── scripts/
│   └── collector.py        # Headless live snapshot collector (cron/background)
├── viz/
│   ├── heatmap.py          # Folium map: raster overlay, sensor dots, popups, legend
│   └── charts.py           # (empty) Sidebar charts, AQI gauge — future use
└── utils/
    └── cache.py            # (empty) Caching helpers — future use
```

---

## Data Sources

| Source | Purpose | Notes |
|---|---|---|
| PurpleAir | Live + historical PM₂.₅ | Primary sensor network, EPA-corrected |
| OpenAQ | Live PM₂.₅ | Reference-grade monitors, secondary source |
| OpenWeatherMap | Live wind speed + direction | Free tier |
| TomTom Traffic | Real-time congestion | 2,500 req/day free tier |
| OpenStreetMap / Overpass | Street geometry | No API key needed |
| Meteostat (NOAA ISD) | Historical wind | Training pipeline only, no key |

All free tier. No credit card required.

---

## Algorithm

**Ingestion:** PurpleAir A/B channel validation filters noisy sensors row-by-row. EPA correction applied at the source: `PM₂.₅ = 0.52 × raw − 0.085 × RH + 5.71`. OpenAQ reference data is not corrected (already calibrated). A `source` column is preserved through the pipeline for auditability.

**Interpolation:** IDW on a 200×200 grid over the Dallas bounding box. Longitude deltas are cosine-corrected for Dallas latitude (~32.78°) to avoid ~19% east-west distortion. Grid cells use the 5 nearest sensors with IDW-weighted averaging to eliminate Voronoi-cell artifacts.

**Adjustments:** Post-IDW, each grid cell gets traffic and wind corrections applied. Traffic uses an exponential curve above a congestion threshold. Wind uses per-cell cosine similarity between the wind vector and the bearing from each sensor — downwind cells get pollution added, upwind cells get it reduced. Sensor readings themselves are never modified; adjustments only apply to interpolated grid cells where IDW has no road or wind context.

**Rendering:** Final grid is Gaussian-smoothed and rendered as a PNG raster (ImageOverlay). Click popups use a sparse 30×30 transparent rectangle grid subsampled from the full 200×200 grid.

---

## Phase Roadmap

| Phase | Feature | Status |
|---|---|---|
| 1 | Project scaffold + PurpleAir ingest | ✅ Complete |
| 2 | IDW interpolation + Folium heatmap | ✅ Complete |
| 3 | TomTom + OpenWeatherMap fusion | ✅ Complete |
| 4 | Random Forest model | ✅ Infrastructure complete — model deferred (see below) |
| 5 | Route Optimizer | 🔄 In progress |

**Phase 4 note:** A full training pipeline was built and validated over 180 days of PurpleAir history (68,407 rows, 19 sensors). Two Random Forest approaches were evaluated — raw PM₂.₅ prediction and IDW residual correction. Both failed to outperform the IDW + adjust_grid baseline (raw IDW RMSE 2.48 µg/m³ vs RF residual 2.91). The training infrastructure, negative-result documentation, and spatial features (highway distance via OSMnx) were retained. The dashboard runs on IDW + adjust_grid. Full writeup in `ml/docs/PHASE4_RESULT.md`.

---

## Setup

```bash
git clone https://github.com/aarushm-cloud/dfw-airquality.git
cd dfw-airquality

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this):

PURPLEAIR_API_KEY=your_key_here
OPENAQ_API_KEY=your_key_here
OPENWEATHERMAP_API_KEY=your_key_here
TOMTOM_API_KEY=your_key_here

```bash
streamlit run app.py
```

---

## Background Collector

```bash
python scripts/collector.py               # polls every 30 minutes (default)
python scripts/collector.py --interval 15 # polls every 15 minutes
```

Writes to `data/dashboard_snapshots.csv`. Independent of the ML training set.

---

## Dallas Coverage

North: 33.08 / South: 32.55 / East: -96.46 / West: -97.05

19 of 27 sensors survived A/B validation. 7 of 16 grid cells are empty, clustered in southern and far-eastern DFW (CV=1.21). Low-confidence regions will be tagged in the UI.

---

## Tech Stack

Python 3.10+ · Streamlit · Folium · GeoPandas · Shapely · Scikit-learn · SciPy · Matplotlib · OSMnx · Meteostat · APScheduler · pyarrow · python-dotenv · requests-cache
