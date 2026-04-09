# data/weather.py — OpenWeatherMap current weather ingestion
# Fetches wind speed and direction for Dallas city center.
# One API call covers the whole metro — wind is uniform enough at this scale.

import os
import requests
from dotenv import load_dotenv
from config import MAP_CENTER

load_dotenv()

OWM_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def fetch_wind() -> dict:
    """
    Returns a dict with keys: wind_speed (m/s), wind_deg (0–360 degrees).
    wind_deg is the direction the wind is coming FROM (meteorological standard).
    Returns zeros on failure so the rest of the pipeline can continue.
    """
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("OPENWEATHERMAP_API_KEY is not set in your .env file.")

    params = {
        "lat":   MAP_CENTER[0],
        "lon":   MAP_CENTER[1],
        "appid": api_key,
        "units": "metric",
    }

    response = requests.get(OWM_BASE_URL, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    wind = data.get("wind", {})

    return {
        "wind_speed": wind.get("speed", 0.0),  # m/s
        "wind_deg":   wind.get("deg",   0.0),  # degrees, 0=N, 90=E, 180=S, 270=W
    }
