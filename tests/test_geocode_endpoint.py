"""Tests for GET /api/geocode/suggest — typeahead proxy for LocationIQ.

Mocks `requests.get` at api.routes.geocode's import site so tests don't
hit the live LocationIQ API. Each test resets the in-process TTLCache via
the autouse fixture so cache state can't leak between cases.
"""

import pytest
import requests
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.main import app
from api.routes import geocode

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cache_and_env(monkeypatch):
    """Wipe the suggest cache and pin a known-good API key so tests can't
    leak each other's state."""
    geocode._suggest_cache.clear()
    monkeypatch.setenv("LOCATIONIQ_API_KEY", "test-key")
    yield
    geocode._suggest_cache.clear()


def _fake_resp(payload, status=200):
    class FakeResp:
        status_code = status
        def raise_for_status(self):
            if status >= 400:
                raise requests.HTTPError(f"{status} error")
        def json(self):
            return payload
    return FakeResp()


def _locationiq_payload(*items: tuple[str, str, str]) -> list[dict]:
    """Build a stub LocationIQ autocomplete response. Items are
    (display_name, lat_str, lon_str) — strings on purpose to mirror the
    shape the live API returns."""
    return [
        {
            "place_id": f"pid-{i}",
            "display_name": dn,
            "lat": lat,
            "lon": lon,
            # Extra fields we explicitly DO NOT want surfaced in the
            # frontend contract — included here so tests catch any
            # accidental passthrough.
            "boundingbox": ["32.0", "33.0", "-97.0", "-96.0"],
            "class": "place", "type": "city",
        }
        for i, (dn, lat, lon) in enumerate(items)
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_suggest_happy_path_returns_normalized_suggestions():
    payload = _locationiq_payload(
        ("Klyde Warren Park, Dallas, TX, USA", "32.7898", "-96.8012"),
        ("Klein, TX, USA", "30.0000", "-95.5000"),
    )
    with patch.object(geocode.requests, "get", return_value=_fake_resp(payload)):
        resp = client.get("/api/geocode/suggest", params={"q": "Klyde", "limit": 5})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2

    # Normalized to {display_name, lat, lon} — provider-specific fields
    # (place_id, class, boundingbox, etc.) must NOT leak through.
    for s in body:
        assert set(s.keys()) == {"display_name", "lat", "lon"}
        assert isinstance(s["lat"], float)
        assert isinstance(s["lon"], float)

    assert body[0]["display_name"].startswith("Klyde Warren Park")
    assert body[0]["lat"] == pytest.approx(32.7898)
    assert body[0]["lon"] == pytest.approx(-96.8012)


def test_suggest_empty_locationiq_response_returns_200_empty_list():
    """Empty typeahead is a valid state — must NOT 404."""
    with patch.object(geocode.requests, "get", return_value=_fake_resp([])):
        resp = client.get("/api/geocode/suggest", params={"q": "qwerasdfzxcv"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_suggest_drops_malformed_items_without_failing():
    """A single bad row in LocationIQ's response shouldn't 500 the proxy."""
    payload = [
        {"display_name": "good", "lat": "32.78", "lon": "-96.80"},
        {"display_name": "bad — missing lon", "lat": "32.78"},
        {"display_name": "bad — non-numeric lat", "lat": "abc", "lon": "-96.80"},
        {"display_name": "good 2", "lat": "32.79", "lon": "-96.81"},
    ]
    with patch.object(geocode.requests, "get", return_value=_fake_resp(payload)):
        resp = client.get("/api/geocode/suggest", params={"q": "Dallas"})
    assert resp.status_code == 200
    assert [s["display_name"] for s in resp.json()] == ["good", "good 2"]


# ---------------------------------------------------------------------------
# Pydantic validation (q min_length, limit bounds)
# ---------------------------------------------------------------------------

def test_suggest_q_too_short_returns_422():
    for short in ("", "a"):
        resp = client.get("/api/geocode/suggest", params={"q": short})
        assert resp.status_code == 422, f"q={short!r} should fail min_length"


def test_suggest_limit_out_of_range_returns_422():
    resp = client.get("/api/geocode/suggest", params={"q": "Klyde", "limit": 11})
    assert resp.status_code == 422
    resp = client.get("/api/geocode/suggest", params={"q": "Klyde", "limit": 0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

def test_suggest_missing_api_key_returns_503(monkeypatch):
    """Both unset and the placeholder value must surface as 503 with the
    'Geocoding service not configured' detail — the frontend uses the
    distinct status to know the feature isn't usable on this backend."""
    for key_value in (None, "your_key_here"):
        if key_value is None:
            monkeypatch.delenv("LOCATIONIQ_API_KEY", raising=False)
        else:
            monkeypatch.setenv("LOCATIONIQ_API_KEY", key_value)
        # No mock — request must fail at env-check before reaching requests.get
        resp = client.get("/api/geocode/suggest", params={"q": "Klyde"})
        assert resp.status_code == 503
        assert "Geocoding service not configured" in resp.json()["detail"]


def test_suggest_locationiq_4xx_returns_502():
    with patch.object(geocode.requests, "get", return_value=_fake_resp({}, status=401)):
        resp = client.get("/api/geocode/suggest", params={"q": "Klyde"})
    assert resp.status_code == 502
    assert "Geocoding upstream error" in resp.json()["detail"]


def test_suggest_locationiq_429_returns_502():
    """Rate-limit specifically — same upstream-error mapping; the proxy
    doesn't pass through the 429 because clients shouldn't retry-storm
    LocationIQ on our key."""
    with patch.object(geocode.requests, "get", return_value=_fake_resp({}, status=429)):
        resp = client.get("/api/geocode/suggest", params={"q": "Klyde"})
    assert resp.status_code == 502


def test_suggest_network_error_returns_502():
    def raise_timeout(*a, **kw):
        raise requests.ConnectTimeout("connection timed out")
    with patch.object(geocode.requests, "get", side_effect=raise_timeout):
        resp = client.get("/api/geocode/suggest", params={"q": "Klyde"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_suggest_cache_hits_on_repeated_query():
    """Two identical queries must hit LocationIQ once. Cache key is
    (q.strip().lower(), limit) — so case and whitespace differences
    around the same logical query also hit the cache on the second call."""
    payload = _locationiq_payload(("Klyde Warren Park", "32.78", "-96.80"))
    call_count = {"n": 0}

    def fake_get(*a, **kw):
        call_count["n"] += 1
        return _fake_resp(payload)

    with patch.object(geocode.requests, "get", side_effect=fake_get):
        # Same logical query, varied casing/whitespace.
        for q in ("Klyde", "klyde", "  KLYDE  "):
            resp = client.get("/api/geocode/suggest", params={"q": q, "limit": 5})
            assert resp.status_code == 200

    assert call_count["n"] == 1, (
        f"three queries of normalized form 'klyde' should hit upstream once; "
        f"got {call_count['n']} calls"
    )
    # Verify the cache actually has the normalized key
    assert ("klyde", 5) in geocode._suggest_cache
