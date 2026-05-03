# AERIA Backend

FastAPI service that wraps the existing DFW air quality pipeline as a JSON API
for the AERIA frontend (Phase 6 UI overhaul). The legacy Streamlit app at
`app.py` keeps running unchanged — this backend only re-exposes `engine/`,
`data/`, and `config.py` as HTTP endpoints.

## Run locally

From the project root with the project venv activated:

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Then open:

- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

The server reads the same `.env` file as the Streamlit app (see `CLAUDE.md`),
so `PURPLEAIR_API_KEY`, `OPENAQ_API_KEY`, `OPENWEATHERMAP_API_KEY`, and
`TOMTOM_API_KEY` must all be set.

### Optional: warm the cache at startup

Setting `AERIA_WARMUP=1` before launching uvicorn kicks off the full grid
pipeline in a background thread at startup, so the first user request is
instant instead of paying the ~20 s cold-start cost.

```bash
AERIA_WARMUP=1 uvicorn api.main:app --reload --port 8000
```

Without the flag the backend behaves exactly as before — lazy load on first
request. The warmup runs on a daemon thread, so `/api/health` and other
endpoints stay responsive while it's priming.

## Environment

| Variable | Default | Description |
|---|---|---|
| `AERIA_WARMUP` | unset | If set to `1`, pre-populates the grid cache in a background thread at startup. |
| `AERIA_CORS_ORIGINS` | unset | Comma-separated list of additional CORS origins. Localhost dev origins (`http://localhost:5173` and `http://127.0.0.1:5173`) are always included. Set in deploy environments to add the production frontend origin (e.g. `https://aeria.vercel.app`). |

The resolved CORS allowlist is logged once at module load as `[cors] active origins: ...` so a misconfigured deploy is immediately obvious in the logs.

## Endpoints

All endpoints are GET-only and live under `/api`. Responses are cached in
memory for 5 minutes (matches the pipeline's existing refresh cadence).

### `GET /api/sensors`

Live PM2.5 readings from PurpleAir + OpenAQ inside the Dallas bounding box.
PurpleAir values are EPA-corrected at ingest; OpenAQ values are reference-grade.

```json
{
  "count": 87,
  "timestamp": "2026-05-01T17:23:11+00:00",
  "sensors": [
    {
      "sensor_id": "12345",
      "name": "Downtown Dallas",
      "lat": 32.78,
      "lon": -96.80,
      "pm25": 9.4,
      "pm25_raw": 12.1,
      "epa_corrected": 1,
      "source": "purpleair"
    }
  ]
}
```

### `GET /api/grid`

Full pipeline result: ingest → IDW → traffic/wind adjustment. Returns the
`GRID_RESOLUTION` × `GRID_RESOLUTION` PM2.5 grid plus a matching confidence
grid. **First call is slow** (5–15 seconds end-to-end including TomTom polling);
cached calls are instant.

```json
{
  "timestamp": "2026-05-01T17:23:11+00:00",
  "resolution": 200,
  "bbox": {"north": 33.08, "south": 32.55, "east": -96.46, "west": -97.05},
  "lats": [32.55, ..., 33.08],
  "lons": [-97.05, ..., -96.46],
  "pm25": [[9.4, 9.5, ...], ...],
  "confidence": [[0.81, 0.79, ...], ...],
  "wind_speed": 3.2,
  "wind_deg": 180.0,
  "sensor_count": 87,
  "avg_pm25": 9.8
}
```

`lats` and `lons` are returned as 1D arrays because both axes are regular
linspaces — full 2D meshes are reconstructable on the frontend without
shipping 40k duplicated floats.

### `GET /api/cells/{zip}`

Look up a US zip code, find the closest cell on the grid, and return that
cell's PM2.5, AQI category, neighborhood, and confidence. Uses the same
cached pipeline snapshot as `/api/grid`.

```json
{
  "zip": "75201",
  "lat": 32.78,
  "lon": -96.80,
  "cell_lat": 32.781,
  "cell_lon": -96.798,
  "cell_i": 137,
  "cell_j": 95,
  "pm25": 11.2,
  "aqi_category": "good",
  "confidence": 0.92,
  "neighborhood": "Dallas",
  "timestamp": "2026-05-01T17:23:11+00:00"
}
```

Returns 404 if the zip is unknown or falls outside the Dallas bounding box.

### `GET /api/health`

Cheap liveness + cache-warm probe. Hit by the frontend on every page load.
Does no I/O.

```json
{ "status": "ok", "cache_warm": true, "uptime_seconds": 142 }
```

`cache_warm` flips to `true` once the grid pipeline has been run at least
once (either by a real request or by `AERIA_WARMUP=1`).

## Development tools

### OpenAPI snapshot

`api/scripts/snapshot_openapi.py` writes `api/openapi.snapshot.json` —
a pretty-printed, sorted-keys dump of the live FastAPI schema. Run it
manually whenever you want a fresh contract baseline:

```bash
python api/scripts/snapshot_openapi.py
```

Diffing the snapshot across commits surfaces unintended API contract
changes. Not automated — the developer runs it on demand.

## Architecture notes

- The backend is a **thin wrapper** — it imports `engine/`, `data/`, and
  `config.py` and does not duplicate logic. Any change to the pipeline lands
  here automatically the next time the cache expires.
- Caching is a small in-memory TTL dict per route. `routes/grid.py` owns the
  shared pipeline snapshot; `routes/cells.py` reads from the same snapshot
  so the two endpoints stay coherent within a single 5-minute window.
- CORS is built from two sources at startup: the always-included localhost
  dev origins and the comma-separated `AERIA_CORS_ORIGINS` env var. See the
  Environment section above for deploy configuration.
