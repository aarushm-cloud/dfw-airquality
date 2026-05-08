"""
Tests for the consolidated uszipcode-based zip lookup — covers audit
issue #17.

The point of the consolidation is that a single library now handles both
forward (zip → coords) and reverse (coords → zip) lookups across both the
Streamlit `viz/heatmap.py` and the FastAPI `api/routes/cells.py` paths.
This test pins the happy-path behaviour for one well-known DFW coordinate
through both code paths.

ZIP 75201 is downtown Dallas — central enough that any reasonable
nearest-zip lookup over the metro must return a Dallas-area result.
"""

import pytest

from viz.heatmap import _coords_to_zip, zip_to_coords


# Downtown Dallas city hall area — 32.78°N, -96.80°W resolves to 75202 in
# uszipcode's simple DB. We assert "starts with 752" rather than an exact
# string so a future DB refresh that picks 75201 over 75202 doesn't break
# the test on a non-meaningful change.
DOWNTOWN_DALLAS_LAT = 32.78
DOWNTOWN_DALLAS_LON = -96.80


def test_reverse_lookup_resolves_dfw_coord_to_dallas_zip():
    """`_coords_to_zip` (used by the heatmap popups) must resolve a
    downtown-Dallas coordinate to a Dallas-area zip via uszipcode."""
    zip_code = _coords_to_zip(DOWNTOWN_DALLAS_LAT, DOWNTOWN_DALLAS_LON)
    assert zip_code is not None, (
        "downtown Dallas coord must resolve to *some* zip via uszipcode"
    )
    assert zip_code.startswith("752"), (
        f"expected a Dallas-area (752xx) zip, got {zip_code!r}"
    )


def test_forward_lookup_round_trips_known_zip():
    """`zip_to_coords` (used by the future zip-search feature) must
    round-trip a known DFW zip back to coordinates inside the metro
    bounding box."""
    coords = zip_to_coords("75201")
    assert coords is not None, "75201 (downtown Dallas) must be in the DB"
    lat, lon = coords
    # Loose Dallas-metro envelope; the project's actual BBOX would be
    # tighter but this test runs without importing config.
    assert 32.5 < lat < 33.1, f"75201 lat outside Dallas metro: {lat}"
    assert -97.1 < lon < -96.4, f"75201 lon outside Dallas metro: {lon}"


def test_forward_lookup_returns_none_for_invalid_zip():
    """uszipcode returns a SimpleZipcode with all-None fields for an
    unknown zip rather than returning None outright. The wrapper has to
    detect that and surface None to its callers."""
    assert zip_to_coords("99999") is None


@pytest.mark.parametrize("zip_code", ["75201", "76102"])  # Dallas, Fort Worth
def test_forward_lookup_smoke_for_known_dfw_zips(zip_code):
    """Sanity for two well-known DFW-area zips. If either of these breaks,
    the uszipcode DB has shifted in a way worth flagging.

    Note: 76101 (Fort Worth) is intentionally NOT used here — it's a
    PO-Box-only zip with no coordinates in the simple DB. 76102 is the
    geographic Fort Worth downtown zip and has populated lat/lng.
    """
    assert zip_to_coords(zip_code) is not None
