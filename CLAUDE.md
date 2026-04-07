# DFW Air Quality Dashboard — Project Context for Claude

## Project Goal
A real-time, street-level air quality dashboard for the Dallas, TX metro area.
This is a personal tool (not academic, not a demo) that predicts PM₂.₅ respiratory
risk by fusing live IoT sensor data, traffic congestion, and weather data, then
visualizes it as an interactive heatmap with a "cleanest route" optimizer.

---

## Tech Stack (Locked)

| Layer         | Tool                                      |
|---------------|-------------------------------------------|
| Language      | Python 3.10+                              |
| UI            | Streamlit                                 |
| Mapping       | Folium (Phase 1–3) → Plotly Mapbox later  |
| Geospatial    | GeoPandas, Shapely                        |
| ML            | Scikit-learn                              |
| HTTP          | Requests + requests-cache                 |
| Scheduling    | APScheduler                               |
| Env/Secrets   | python-dotenv                             |
| Version Control | Git + GitHub                            |
| Deployment    | Streamlit Cloud                           |

---

## APIs (All Free Tier)

| API               | Purpose                          | Notes                                      |
|-------------------|----------------------------------|--------------------------------------------|
| PurpleAir         | Live PM₂.₅ sensor data          | Primary air quality source                 |
| OpenWeatherMap    | Wind speed and direction         | Free tier is sufficient                    |
| TomTom Traffic    | Real-time congestion data        | 2,500 req/day free — enough for personal use |
| OpenStreetMap / Overpass | Street & building geometry | Fully free, no API key needed           |

**Note:** Google Maps was intentionally dropped. TomTom handles traffic,
OSM handles geometry, and this avoids requiring a credit card.

---

## Project Folder Structure

```
dfw-airquality/
├── app.py                  # Streamlit entry point
├── CLAUDE.md               # This file — always read at session start
├── .env                    # API keys (gitignored — never commit this)
├── .gitignore
├── requirements.txt
├── config.py               # Constants: bounding box, refresh intervals, AQI thresholds
├── data/
│   ├── purpleair.py        # PurpleAir ingestion
│   ├── weather.py          # OpenWeatherMap ingestion
│   ├── traffic.py          # TomTom ingestion
│   └── osm.py              # Overpass / OSM geometry fetching
├── engine/
│   ├── interpolation.py    # IDW interpolation (Phase 2), Random Forest (Phase 4)
│   ├── features.py         # Feature engineering: sensor proximity, traffic, wind
│   └── router.py           # Route optimizer — cleanest path (Phase 5)
├── viz/
│   ├── heatmap.py          # Folium map builder
│   └── charts.py           # Sidebar charts, AQI gauge
└── utils/
    └── cache.py            # Caching helpers
```

---

## Phased Build Plan

| Phase | Feature                              | End State                                      |
|-------|--------------------------------------|------------------------------------------------|
| 1     | Project scaffold + PurpleAir ingest  | Live PM₂.₅ sensor dots on a Dallas map        |
| 2     | IDW interpolation + Folium heatmap   | Smooth PM₂.₅ heatmap over Dallas              |
| 3     | TomTom + OpenWeatherMap fusion       | Traffic & wind factored into the model         |
| 4     | Random Forest replaces IDW           | Smarter, more accurate predictions             |
| 5     | Route Optimizer                      | Suggests cleanest walking/biking path          |

**Always complete one phase fully before starting the next.**

---

## Current Status

- [ ] Phase 1 — Not started
- [ ] Phase 2 — Not started
- [ ] Phase 3 — Not started
- [ ] Phase 4 — Not started
- [ ] Phase 5 — Not started

**Update this section at the start of each Claude session.**

---

## Developer Setup Notes

- **OS / Environment:** Python 3.10+, venv for virtual environments
- **IDE:** VS Code with Claude Code extension
- **GitHub:** Repo not yet created — needs to be initialized

### First-Time Setup (run once)
```bash
# From inside the project folder
python -m venv venv

# Activate (Mac/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

### .env file format (never commit this file)
```
PURPLEAIR_API_KEY=your_key_here
OPENWEATHERMAP_API_KEY=your_key_here
TOMTOM_API_KEY=your_key_here
```

---

## Key Decisions & Reasoning

- **IDW before Random Forest:** IDW is simpler and gets a working heatmap fast.
  Random Forest gets added in Phase 4 once the full pipeline is proven.
- **Folium before Plotly Mapbox:** Folium is easier to start with and has no
  additional API key requirement. Plotly Mapbox can replace it later for a
  more polished UI.
- **Dropped Kriging:** Statistically heavy, not worth the complexity for this use case.
- **Dropped Google Maps:** TomTom + OSM cover all needed functionality for free,
  with no credit card required.
- **APScheduler for refresh:** Keeps sensor/traffic/weather data fresh on a
  configurable interval without requiring the user to manually reload.

---

## Dallas Bounding Box (for map and API queries)
```
North: 33.08
South: 32.55
East:  -96.46
West:  -97.05
```

---

## Notes for Claude at Session Start

- Read this file first before doing anything.
- Ask the user which phase they are on and what they want to work on today.
- Do not refactor code from previous phases unless the user asks.
- Keep functions small and well-commented — the developer is intermediate level.
- Prefer explicit, readable code over clever one-liners.
- Always update requirements.txt when adding a new library.
