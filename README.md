# DFW Air Quality Dashboard

A real-time, street-level PM₂.₅ air quality dashboard for the Dallas–Fort Worth metro area. Fuses live IoT sensor data, traffic congestion, and weather into an interpolated heatmap — with a cleanest-route optimizer for walking and biking paths.

---

## What It Does

- Pulls live PM₂.₅ readings from **27 PurpleAir sensors** across the DFW metro and supplements them with **OpenAQ** reference monitors
- Applies **EPA correction** (AirNow Fire and Smoke Map formula) to raw PurpleAir readings using humidity
- Interpolates a smooth **200×200 PM₂.₅ grid** using IDW (Inverse Distance Weighting) with cosine-corrected distance calculations for Dallas latitude
- Adjusts the interpolated grid using **live TomTom traffic congestion** (exponential curve weighting) and **OpenWeatherMap wind direction** (per-cell cosine similarity factor)
- Renders as a **Gaussian-smoothed raster overlay** on an interactive Folium map — not 40,000 DOM rectangles
- Accumulates live snapshots for drift monitoring and ML training

---

## Architecture

```
dfw-airquality/
├── app.py                  # Streamlit entry point
├── .env                    # API keys (gitignored — never commit this)
├── .gitignore
├── requirements.txt
├── config.py               # Constants: bounding box, grid, IDW, traffic/wind params
├── data/
│   ├── ingestion/                   # Live API fetchers
│   │   ├── purpleair.py             # PurpleAir live ingestion (EPA-corrected)
│   │   ├── openaq.py                # OpenAQ v3 ingestion (secondary PM2.5 source)
│   │   ├── weather.py               # OpenWeatherMap ingestion (live wind)
│   │   ├── traffic.py               # TomTom ingestion (8×8 sample grid, live)
│   │   └── history.py               # Live dashboard snapshot accumulator
│   ├── spatial/
│   │   └── spatial_features.py      # OSMnx highway-distance feature builder
│   ├── dashboard_snapshots.csv      # Accumulated live snapshots
│   └── .cache/                      # OSMnx + other cached fetches
├── engine/
│   ├── adjustments.py      # Shared traffic/wind math (scalar + vectorised)
│   ├── interpolation.py    # IDW interpolation + post-IDW grid adjustments
│   ├── features.py         # Per-sensor live feature columns
│   └── router.py           # Cleanest-route optimizer
├── ml/
│   ├── predictor.py                 # Random Forest inference
│   ├── training/
│   │   └── collect_training_data.py # Canonical training-data builder
│   ├── analysis/
│   │   ├── sensor_coverage_check.py
│   │   ├── openaq_coverage_check.py
│   │   └── output/                  # Generated PNGs / CSVs
│   ├── models/                      # .pkl files (gitignored)
│   ├── data/                        # ML-specific data artifacts
│   │   ├── history.csv              # Training set (gitignored)
│   │   ├── quality_report.json      # Quality report
│   │   ├── collection_log.txt       # Audit log
│   │   └── .checkpoints/            # Per-sensor parquet resume points
│   └── docs/                        # Algorithm documentation
├── scripts/
│   └── collector.py        # Headless live snapshot collector (cron/background)
├── viz/
│   └── heatmap.py          # Folium map: raster overlay, sensor dots, popups, legend
├── api/                              # FastAPI backend wrapping engine/, data/, config.py
│   ├── main.py
│   ├── routes/
│   │   ├── health.py                 # /health — backend liveness
│   │   ├── sensors.py                # /sensors — live PurpleAir + OpenAQ readings
│   │   ├── grid.py                   # /grid — interpolated 200×200 PM₂.₅ grid
│   │   └── cells.py                  # /cells/{id} — per-cell breakdown + attribution
│   └── schemas/                      # Pydantic response models
└── web/                              # Vite + React + TypeScript + R3F frontend (AERIA)
    ├── src/
    │   ├── App.tsx
    │   ├── api/client.ts             # Typed fetch layer for FastAPI
    │   ├── state/                    # Zustand stores (sensors, grid, scene, view, connection)
    │   ├── world/                    # Pure helpers: AQI, bbox math, building generation, health guidance
    │   └── components/
    │       ├── scene/                # R3F: CityScene, StreetScene, CellGrid, Buildings, Particles
    │       └── ui/                   # TopNav, TopStatusBar, LeftPanel, CellInfoCard, ZipSearch
    └── docs/                         # Session screenshots / design references
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

**Modeling:** A Random Forest pipeline was built and validated over 180 days of PurpleAir history (68,407 rows, 19 sensors). Two approaches were evaluated — raw PM₂.₅ prediction and IDW residual correction. Neither outperformed the IDW + adjust_grid baseline on RMSE (2.48 µg/m³ vs 2.91 for the RF residual model), so the dashboard ships with the deterministic baseline. Training infrastructure and spatial features (highway distance via OSMnx) are retained for future iterations. Full writeup in [`ml/docs/`](ml/docs/).

**Rendering:** Final grid is Gaussian-smoothed and rendered as a PNG raster (ImageOverlay). Click popups use a sparse 30×30 transparent rectangle grid subsampled from the full 200×200 grid.

---

## AERIA — 3D Web Dashboard

The custom frontend (`web/`) is the primary interface. It replaces the Folium/Streamlit map with a stylized 3D scene built in React Three Fiber, backed by a FastAPI service (`api/`) that wraps the existing Python engine as JSON endpoints.

**Two primary views**
- **City overview** — top-down isometric scene of the DFW bounding box with a clickable cell grid, generated buildings, and PM₂.₅-driven particle ambience. Hovering surfaces a cell info card; clicking selects the cell and updates the side panel.
- **Street view** — first-person ground-level scene the user drops into when they pick a cell. The geometry is reusable; only the air-quality state changes per cell.

**Persistent left panel** — AQI category, current PM₂.₅ reading with 24h delta and attribution line ("EPA-corrected · IDW from N nearby sensors"), AQI-driven health guidance for sensitive groups and the general public, activity guidance (outdoor exercise, windows, masks), and a per-cell breakdown (traffic adjustment, wind adjustment, highway distance, last updated).

**Top status bar** — live indicator with sensor count, network-average PM₂.₅, wind speed and direction, and an "updated N min ago" timestamp.

**ZIP search** — jump the camera and selection straight to any DFW ZIP.

### In progress / roadmap

- **Time machine tab** — historical playback over the accumulated `dashboard_snapshots.csv`
- **Route lab tab** — cleanest-path optimizer wired to `engine/router.py`
- **Live sensor pulses** — animated dots on the city scene driven by real PurpleAir update events
- **Backend deploy** — Render free tier for `api/`, Vercel for `web/` (currently runs locally via `dev.sh`)
- **Streamlit retirement** — the Streamlit app stays online until AERIA reaches feature parity, then gets removed

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

## Local development

The project ships with a FastAPI backend (`api/`) and a React + R3F frontend
(`web/`) alongside the original Streamlit app. Use `dev.sh` to launch the dev
stack:

```bash
./dev.sh                                    # FastAPI backend on :8000 (auto-reload)
./dev.sh --with-streamlit                   # also start the Streamlit app on :8501
./dev.sh --with-frontend                    # also start the Vite dev server on :5173
./dev.sh --with-streamlit --with-frontend   # all three at once
```

Output from each process is prefixed (`[api]`, `[streamlit]`, `[web]`) so the
multiplexed log stays scannable. Ctrl+C cleans up every child process.

The frontend lives in [`web/`](web/) — see `web/README.md` for setup.

---

## Background Collector

```bash
python scripts/collector.py               # polls every 30 minutes (default)
python scripts/collector.py --interval 15 # polls every 15 minutes
```

Writes to `data/dashboard_snapshots.csv`. Independent of the ML training set.

---

## Dallas Coverage

Bounding box: N 33.08 / S 32.55 / E -96.46 / W -97.05

19 of 27 sensors pass A/B validation on a typical run. 7 of 16 macro grid cells are sparsely covered, clustered in southern and far-eastern DFW (CV=1.21) — these regions are flagged as low-confidence in the dashboard.

---

## Tech Stack

Python 3.10+ · FastAPI · Streamlit · React · TypeScript · React Three Fiber · Vite · Folium · GeoPandas · Shapely · Scikit-learn · SciPy · Matplotlib · OSMnx · Meteostat · APScheduler · pyarrow · python-dotenv · requests-cache
