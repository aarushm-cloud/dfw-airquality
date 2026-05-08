"""
Tests for `data.ingestion.openaq._parse_reading_timestamp` — covers audit
issue #8.

The OpenAQ v3 API has been observed to return timestamps in three shapes:
a `Z` suffix, an explicit `+HH:MM` offset, and (occasionally, on the
nested `{"utc": "..."}` form) no timezone marker at all. The third case
parses as naive and would crash the subsequent
`datetime.now(timezone.utc) - reading_dt` subtraction. Per-location
try/except contains the blast radius to one dropped reading per
offending location, but those readings are recoverable — they're meant
to be UTC.

The helper exists specifically so this regression has a unit-testable
seam.
"""

from datetime import datetime, timezone, timedelta

from data.ingestion.openaq import _parse_reading_timestamp


def test_parses_z_suffix_as_utc():
    """`Z` suffix → tz-aware, UTC. The fromisoformat-incompatible Z is
    normalised to +00:00 before parsing."""
    parsed = _parse_reading_timestamp("2026-05-07T12:00:00Z")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_parses_explicit_utc_offset():
    """`+00:00` → tz-aware, UTC. fromisoformat handles this natively."""
    parsed = _parse_reading_timestamp("2026-05-07T12:00:00+00:00")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_naive_timestamp_is_treated_as_utc():
    """The regression: a string with no tz marker must come back tz-aware,
    UTC. Without this, the subtraction in the caller would raise
    TypeError and one reading per offending location would be dropped."""
    parsed = _parse_reading_timestamp("2026-05-07T12:00:00")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_non_utc_offset_is_preserved_not_rewritten():
    """A timestamp with an explicit non-UTC offset must NOT be silently
    rewritten to UTC. The naive-as-UTC fallback is intentionally narrow:
    it only runs when tzinfo is None. An IST timestamp (`+05:30`) keeps
    its offset and represents the same instant as 06:30 UTC."""
    parsed = _parse_reading_timestamp("2026-05-07T12:00:00+05:30")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(hours=5, minutes=30)
    # Same instant in UTC.
    assert parsed.astimezone(timezone.utc) == datetime(
        2026, 5, 7, 6, 30, 0, tzinfo=timezone.utc
    )


def test_subtraction_against_utc_now_does_not_raise():
    """Behavioural check: the whole point is that the parsed datetime
    must be subtractable from `datetime.now(timezone.utc)` without a
    TypeError, for every shape we accept."""
    for ts in (
        "2026-05-07T12:00:00Z",
        "2026-05-07T12:00:00+00:00",
        "2026-05-07T12:00:00",
        "2026-05-07T12:00:00+05:30",
    ):
        parsed = _parse_reading_timestamp(ts)
        # Just need this to not raise.
        _ = (datetime.now(timezone.utc) - parsed).total_seconds()
