"""GET /api/geocode/suggest — server-side proxy for LocationIQ autocomplete.

Keeps the LocationIQ key off the wire (browser never sees it) and lets the
backend cache typeahead queries with a 10-minute TTL. The frontend Route
Lab tab (item 3) calls this endpoint as the user types.

Note: this is a typeahead proxy only. POST /api/route still re-geocodes
via engine.router's /v1/search call — the LRU cache there catches dupes
when the user picks a suggestion the typeahead already resolved.
"""

import logging
import os

import requests
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from config import BBOX

from api.schemas.responses import GeocodeSuggestion

logger = logging.getLogger(__name__)
router = APIRouter()

# LocationIQ autocomplete returns the same flat-list / string-coords shape
# as /v1/search — no `format=geojson` paid-tier dependency. We hit the
# extension-less endpoint variant; both `/v1/autocomplete.php` and
# `/v1/autocomplete` resolve identically.
LOCATIONIQ_AUTOCOMPLETE_URL = "https://us1.locationiq.com/v1/autocomplete"

# 10-minute TTL strikes a balance between fresh-enough suggestions and
# burning the 5,000/day free-tier budget on identical typeahead bursts.
# Same daily-quota reset semantics as engine.router (00:00 UTC).
_suggest_cache: TTLCache = TTLCache(maxsize=10_000, ttl=600)


def _locationiq_key() -> str:
    key = os.getenv("LOCATIONIQ_API_KEY")
    if not key or key == "your_key_here":
        raise HTTPException(status_code=503, detail="Geocoding service not configured")
    return key


@router.get("/geocode/suggest", response_model=list[GeocodeSuggestion], tags=["geocode"])
def suggest(
    q: str = Query(min_length=2, description="Partial address text"),
    limit: int = Query(default=5, ge=1, le=10, description="Max suggestions"),
) -> list[GeocodeSuggestion]:
    cache_key = (q.strip().lower(), limit)
    cached = _suggest_cache.get(cache_key)
    if cached is not None:
        return cached

    params = {
        "key": _locationiq_key(),
        "q": q,
        "limit": limit,
        # Soft bias only — out-of-DFW results stay visible in the dropdown
        # so a user typing "Times Square NY" sees something rather than
        # silent emptiness, even though /api/route would later reject it.
        "viewbox": f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}",
    }
    try:
        resp = requests.get(LOCATIONIQ_AUTOCOMPLETE_URL, params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("LocationIQ autocomplete failure for %r: %s", q, e)
        raise HTTPException(status_code=502, detail="Geocoding upstream error")

    if not isinstance(payload, list):
        # Empty / unexpected shape — not strictly an upstream error, but
        # we only know how to handle the documented flat-list response.
        _suggest_cache[cache_key] = []
        return []

    suggestions: list[GeocodeSuggestion] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            suggestions.append(GeocodeSuggestion(
                display_name=str(item.get("display_name", "")),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
            ))
        except (KeyError, TypeError, ValueError):
            # Drop malformed items rather than 500 on a single bad record.
            continue

    _suggest_cache[cache_key] = suggestions
    return suggestions
