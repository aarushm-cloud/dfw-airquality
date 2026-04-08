# config.py — Project-wide constants

# Dallas metro bounding box
BBOX = {
    "north": 33.08,
    "south": 32.55,
    "east": -96.46,
    "west": -97.05,
}

# Map center (approximate center of Dallas)
MAP_CENTER = [32.815, -96.755]
MAP_ZOOM = 10

# Data refresh interval in seconds (used by APScheduler)
REFRESH_INTERVAL_SECONDS = 300  # 5 minutes

# AQI / PM2.5 thresholds (µg/m³) — EPA breakpoints
AQI_THRESHOLDS = {
    "good":        (0, 12),
    "moderate":    (12.1, 35.4),
    "sensitive":   (35.5, 55.4),
    "unhealthy":   (55.5, 150.4),
    "very_unhealthy": (150.5, 250.4),
    "hazardous":   (250.5, 9999),
}

# Color mapping for AQI categories (used on the map markers)
AQI_COLORS = {
    "good":           "green",
    "moderate":       "yellow",
    "sensitive":      "orange",
    "unhealthy":      "red",
    "very_unhealthy": "purple",
    "hazardous":      "darkred",
}

# PurpleAir API base URL
PURPLEAIR_BASE_URL = "https://api.purpleair.com/v1"
