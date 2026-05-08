"""
Tests for `data.ingestion.traffic._congestion_score` — covers audit issue #14.

The TomTom Flow API occasionally returns a `freeFlowSpeed` of 0 (or
even negative) when its segment lookup fails. The pre-existing code
silently returned 0.0 in that branch, which downstream means the cell
gets *no* traffic adjustment — indistinguishable from a genuinely free
road. We keep that 0.0 contract (it's the conservative choice) but
also emit a WARNING so bad-data rate is observable in logs.
"""

import logging

import pytest

from data.ingestion.traffic import _congestion_score


# ---------------------------------------------------------------------------
# Happy path — confirm the scoring math is unchanged
# ---------------------------------------------------------------------------

def test_positive_free_flow_returns_expected_score():
    """50 / 100 = 0.5 ratio → 0.5 congestion score."""
    score = _congestion_score(current_speed=50.0, free_flow_speed=100.0)
    assert score == pytest.approx(0.5)


def test_full_free_flow_returns_zero():
    """current_speed == free_flow_speed → 1.0 ratio → 0.0 congestion."""
    score = _congestion_score(current_speed=60.0, free_flow_speed=60.0)
    assert score == pytest.approx(0.0)


def test_stopped_traffic_returns_one():
    """current_speed = 0 with positive free-flow → maximum congestion."""
    score = _congestion_score(current_speed=0.0, free_flow_speed=60.0)
    assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Bad upstream data — must return 0.0 AND emit a WARNING
# ---------------------------------------------------------------------------

def test_zero_free_flow_returns_zero_and_warns(caplog):
    """free_flow_speed == 0 is the canonical bad-data signal. Contract is
    return 0.0; observability is one WARNING per call."""
    with caplog.at_level(logging.WARNING, logger="data.ingestion.traffic"):
        score = _congestion_score(current_speed=20.0, free_flow_speed=0.0)

    assert score == 0.0

    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1, (
        f"expected exactly one WARNING for zero free-flow, got {len(warns)}"
    )
    msg = warns[0].getMessage()
    assert "non-positive free_flow_speed" in msg
    assert "0" in msg  # the offending value is in the message


def test_negative_free_flow_returns_zero_and_warns(caplog):
    """Negative free-flow is even more obviously bad data than zero. Same
    contract: 0.0 plus a WARNING."""
    with caplog.at_level(logging.WARNING, logger="data.ingestion.traffic"):
        score = _congestion_score(current_speed=20.0, free_flow_speed=-5.0)

    assert score == 0.0

    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1, (
        f"expected exactly one WARNING for negative free-flow, got {len(warns)}"
    )
    assert "-5" in warns[0].getMessage()


def test_positive_free_flow_does_not_warn(caplog):
    """Sanity: the WARNING must only fire on the bad-data branch, not on
    every call."""
    with caplog.at_level(logging.WARNING, logger="data.ingestion.traffic"):
        _congestion_score(current_speed=50.0, free_flow_speed=100.0)

    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warns == [], (
        f"WARNING must not fire on the happy path, got {len(warns)}"
    )
