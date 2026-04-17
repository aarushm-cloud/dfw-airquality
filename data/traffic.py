# data/traffic.py — TomTom Traffic Flow ingestion
#
# Samples congestion at a grid of points across the Dallas bbox.
# TomTom's Flow API returns current vs. free-flow speed for a road segment
# near each point. We convert that to a 0–1 congestion score.

import os
import logging
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from config import BBOX

logger = logging.getLogger(__name__)

load_dotenv()

TOMTOM_FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/18/json"

# How many sample points along each axis — 8x8 = 64 API calls per refresh.
# Stays well within the 2,500/day free tier limit.
SAMPLE_GRID = 8


def _congestion_score(current_speed: float, free_flow_speed: float) -> float:
    """
    Returns a 0–1 score where 0 = free flow, 1 = fully congested.
    Clamps to [0, 1] in case API values are noisy.
    """
    if free_flow_speed <= 0:
        return 0.0
    ratio = current_speed / free_flow_speed
    return float(np.clip(1.0 - ratio, 0.0, 1.0))


def fetch_traffic() -> pd.DataFrame:
    """
    Returns a DataFrame with columns: lat, lon, congestion (0–1).
    Points where the API returns no road data are dropped.
    """
    api_key = os.getenv("TOMTOM_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        raise ValueError("TOMTOM_API_KEY is not set in your .env file.")

    # Build sample grid across the Dallas bbox
    lats = np.linspace(BBOX["south"], BBOX["north"], SAMPLE_GRID)
    lons = np.linspace(BBOX["west"],  BBOX["east"],  SAMPLE_GRID)

    records = []
    error_count = 0

    for lat in lats:
        for lon in lons:
            try:
                resp = requests.get(
                    TOMTOM_FLOW_URL,
                    params={
                        "key":   api_key,
                        "point": f"{lat},{lon}",
                    },
                    timeout=8,
                )
                resp.raise_for_status()
                segment = resp.json().get("flowSegmentData", {})

                current   = segment.get("currentSpeed",  0)
                free_flow = segment.get("freeFlowSpeed",  0)

                records.append({
                    "lat":        lat,
                    "lon":        lon,
                    "congestion": _congestion_score(current, free_flow),
                })

            except Exception as e:
                # Log and skip — one missing road segment shouldn't crash the whole fetch.
                # Auth failures (401), rate limits (429), and network errors all surface here.
                error_count += 1
                logger.debug("TomTom request failed for point (%.4f, %.4f): %s", lat, lon, e)
                continue

    result = pd.DataFrame(records)

    if result.empty and error_count > 0:
        logger.warning(
            "No traffic data retrieved — check API key and network (%d errors logged).",
            error_count,
        )

    return result
