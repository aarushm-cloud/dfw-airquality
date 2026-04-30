# Highway-distance source: OSMnx (live OSM pull, cached on disk).
# Chosen over the static-GeoJSON fallback because the install succeeded
# cleanly. To widen the highway set, change HIGHWAY_FILTER below — the
# next run will refetch and recache automatically.
"""
Static spatial features derived from OpenStreetMap geometry.

The Phase 4 training pipeline needs spatial signals that can be computed
identically at inference time for IDW grid cells. Distance-to-nearest-highway
fits: it's a property of location alone (no time component, no API), so the
same lookup works for historical sensor rows AND live grid cells.
"""

from __future__ import annotations

import logging
import pickle
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from geopy.distance import geodesic
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

# DFW bounding box (matches config.BBOX). Hardcoded here so this module
# stays usable without booting the project's import graph.
DFW_BBOX = {
    "north": 33.08,
    "south": 32.55,
    "east":  -96.46,
    "west":  -97.05,
}

CACHE_DIR  = Path("data/.cache")
CACHE_FILE = CACHE_DIR / "dfw_highways.pkl"
CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days

# OSM tag filter — interstates and US highways in the DFW area
HIGHWAY_FILTER = '["highway"~"motorway|motorway_link|trunk|trunk_link"]'

log = logging.getLogger("dfw_collector")


def _fetch_and_cache_highways() -> list[LineString]:
    """Pull the major-highway network from OSM, save edge geometries to disk."""
    import osmnx as ox  # imported lazily so module import doesn't require it

    # Keep OSMnx's per-request HTTP cache under data/.cache/ instead of
    # littering the repo root with a top-level cache/ directory.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = str(CACHE_DIR / "osmnx_http")

    log.info("  Fetching DFW highway network from OpenStreetMap (one-time, ~30s)")
    bbox = (DFW_BBOX["west"], DFW_BBOX["south"], DFW_BBOX["east"], DFW_BBOX["north"])
    G = ox.graph_from_bbox(
        bbox,
        network_type="drive",
        custom_filter=HIGHWAY_FILTER,
        simplify=True,
    )

    # Convert each edge into a LineString in (lon, lat) order. Edges with a
    # 'geometry' attribute carry the full polyline; the rest are straight
    # lines between their two endpoint nodes.
    geoms: list[LineString] = []
    for u, v, _key, data in G.edges(keys=True, data=True):
        if "geometry" in data:
            geoms.append(data["geometry"])
        else:
            u_node, v_node = G.nodes[u], G.nodes[v]
            geoms.append(LineString([(u_node["x"], u_node["y"]),
                                     (v_node["x"], v_node["y"])]))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("wb") as f:
        pickle.dump(geoms, f)
    log.info(f"  Cached {len(geoms)} highway edges to {CACHE_FILE}")
    return geoms


def _load_highways() -> list[LineString]:
    """Return cached highway LineStrings, refetching if cache is missing or stale."""
    if CACHE_FILE.exists():
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            with CACHE_FILE.open("rb") as f:
                return pickle.load(f)
    return _fetch_and_cache_highways()


# Module-level cache: load the network once per process, not once per call.
_HIGHWAYS: Optional[list[LineString]] = None


def _highways() -> list[LineString]:
    global _HIGHWAYS
    if _HIGHWAYS is None:
        _HIGHWAYS = _load_highways()
    return _HIGHWAYS


@lru_cache(maxsize=4096)
def compute_distance_to_highway(lat: float, lon: float) -> float:
    """Returns geodesic distance in meters from (lat, lon) to the
    nearest major DFW highway segment. Cached on disk."""
    point = Point(lon, lat)
    highways = _highways()

    # Pick the nearest LineString by planar distance (cheap, accurate enough
    # at this scale for *ranking*), then compute geodesic distance to the
    # actual nearest point on that LineString.
    nearest_line = min(highways, key=point.distance)
    on_line, _ = nearest_points(nearest_line, point)
    return geodesic((lat, lon), (on_line.y, on_line.x)).meters
