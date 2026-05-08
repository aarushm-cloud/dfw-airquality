"""
Tests for `data.spatial.spatial_features.compute_distance_to_highway`
caching — covers audit issue #18.

Two layers of cache, both pinned by these tests:

  1. The `lru_cache` on `compute_distance_to_highway` itself — cheap
     per-coordinate hit/miss tracking via `cache_info()`.
  2. The module-level `_HIGHWAYS` snapshot plus its `_HIGHWAYS_MTIME`
     marker, which together let `_highways()` auto-detect a disk-cache
     refresh and self-invalidate. `refresh_highways()` drops both.

The auto-refresh mtime probe is exercised by bumping the disk cache
file's mtime and confirming the next call reloads from disk.

These tests use the real OSMnx-backed cache that's already on disk.
First run will pay the highway-graph fetch (~30s); subsequent runs
ride the disk cache.
"""

import os

import pytest

from data.spatial.spatial_features import (
    CACHE_FILE,
    compute_distance_to_highway,
    refresh_highways,
)


# Downtown Dallas — used as a stable probe point. The exact distance to
# the nearest highway doesn't matter for these tests; we only check
# that repeated calls behave consistently with the cache layer.
PROBE_LAT = 32.78
PROBE_LON = -96.80


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Each test starts with a clean lru_cache and `_HIGHWAYS` slot.
    The disk cache is preserved (we want the real graph) but the
    in-process layers are reset so test order doesn't bleed in."""
    refresh_highways()
    yield
    refresh_highways()


def test_repeated_call_with_same_args_is_cache_hit():
    """Two calls with identical (lat, lon) → first miss, second hit.
    Verified via `cache_info()` so we're not relying on timing."""
    # Prime the cache.
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    info_before = compute_distance_to_highway.cache_info()

    # Same args again → must be a hit, not another miss.
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    info_after = compute_distance_to_highway.cache_info()

    assert info_after.hits == info_before.hits + 1
    assert info_after.misses == info_before.misses


def test_cache_clear_makes_next_call_a_miss():
    """After `cache_clear()` (called inside `refresh_highways()`), the
    same coordinate must miss the lru_cache again — proving the clear
    actually dropped the cached result."""
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    info_before_clear = compute_distance_to_highway.cache_info()
    assert info_before_clear.currsize >= 1

    refresh_highways()
    info_after_clear = compute_distance_to_highway.cache_info()
    assert info_after_clear.currsize == 0

    # Next call after clear → fresh miss.
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    info_after_call = compute_distance_to_highway.cache_info()
    assert info_after_call.misses == info_after_clear.misses + 1


def test_disk_mtime_bump_triggers_auto_refresh():
    """The auto-refresh in `_maybe_refresh_on_mtime_change` watches the disk
    cache file's mtime. Bumping the mtime forward must cause the *next*
    call to invalidate the in-process snapshot before serving — proving
    the auto-trigger actually fires.

    We verify by reading `_HIGHWAYS_MTIME` directly: after the auto-
    refresh, the module's recorded mtime must match the new disk mtime.
    Watching `cache_info()` for this would be misleading because
    `cache_clear()` resets the misses/hits counters, so before/after
    deltas zero out.
    """
    import data.spatial.spatial_features as sf

    # Prime: load highways, capture the recorded mtime.
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    primed_mtime = sf._HIGHWAYS_MTIME
    assert primed_mtime is not None, "test setup: load must record mtime"
    assert CACHE_FILE.exists(), "test setup: disk cache file must exist"

    # Bump the disk-cache mtime forward by 60s without rewriting contents
    # — simulates an out-of-band refresh by another process.
    new_mtime = primed_mtime + 60
    os.utime(CACHE_FILE, (new_mtime, new_mtime))

    # Next call must observe the newer mtime, run refresh_highways, then
    # reload from disk — at which point _HIGHWAYS_MTIME picks up the new
    # value. This is the load-bearing assertion.
    compute_distance_to_highway(PROBE_LAT, PROBE_LON)
    assert sf._HIGHWAYS_MTIME == pytest.approx(new_mtime), (
        "auto-refresh should have reloaded and recorded the new disk mtime"
    )
    assert sf._HIGHWAYS_MTIME > primed_mtime
