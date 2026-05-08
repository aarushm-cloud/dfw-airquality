"""
Tests for `_zip_lookup`'s 404-vs-503 split — covers audit issue #20(a).

The pre-existing behaviour returned 404 for both cases:
  (a) the zip isn't in the database (legitimate not-found)
  (b) the lookup engine itself raised (service-level failure)

(a) and (b) mean very different things to an API consumer — "you typed
a bad zip" versus "we're broken". Splitting them lets the frontend
react appropriately (retry the second, show a "no such zip" message
for the first).

We don't go through the FastAPI app stack here — `_zip_lookup` raises
`HTTPException` regardless of how it's invoked, and asserting on
`exc.status_code` is the cheapest way to pin the contract.
"""

import pytest
from fastapi import HTTPException

from api.routes import cells
from api.routes.cells import _zip_lookup


def test_unknown_zip_raises_404():
    """A zip that isn't in the uszipcode DB → 404. uszipcode returns a
    SimpleZipcode with all-None fields rather than None outright, so the
    function detects that and surfaces the legitimate not-found case."""
    with pytest.raises(HTTPException) as exc_info:
        _zip_lookup("99999")
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()


def test_lookup_engine_failure_raises_503(monkeypatch):
    """If the underlying SearchEngine.by_zipcode raises (e.g. SQLite DB
    is unreadable, library version mismatch, etc.), `_zip_lookup` must
    surface a 503 — distinguishing infrastructure failure from
    legitimate not-found."""

    class BrokenEngine:
        def by_zipcode(self, _zip):
            raise RuntimeError("simulated SQLite read failure")

    monkeypatch.setattr(cells, "_search", BrokenEngine())

    with pytest.raises(HTTPException) as exc_info:
        _zip_lookup("75201")
    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail.lower()
    # Original error message is included so logs/clients can see the cause.
    assert "simulated SQLite read failure" in exc_info.value.detail


def test_known_zip_returns_lat_lon_city():
    """Sanity / contract: a real DFW zip resolves to (lat, lon, city)."""
    lat, lon, place = _zip_lookup("75201")
    assert 32.5 < lat < 33.1
    assert -97.1 < lon < -96.4
    # uszipcode populates `major_city` for a known zip; allow None here in
    # case the underlying DB ever drops the field, but the value-test
    # above is the load-bearing assertion.
    assert place is None or isinstance(place, str)
