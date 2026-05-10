import logging
import os

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

from engine.router import (
    DisconnectedRouteError,
    GeocodeFailure,
    OutOfDFWError,
    Route,
    find_routes,
)

from api.routes.grid import get_cached_snapshot
from api.schemas.requests import RouteRequest
from api.schemas.responses import GeoJSONLineString, RouteResponse, RouteStats

logger = logging.getLogger(__name__)
router = APIRouter()

# Endpoint-layer route cache. Key is the normalized address pair; the
# underlying grid's freshness is validated by comparing snapshot
# timestamps on the cached value at lookup time. This keeps hit rates
# high across grid refreshes for unchanged inputs while guaranteeing
# we never serve stats whose timestamp references a grid that no
# longer exists.
#
# Concurrency note: cachetools.TTLCache is thread-safe for individual
# operations but not for the check-then-write sequence below. Two
# simultaneous misses on the same key will both call find_routes and
# both write. Wasted work, but acceptable at portfolio scale.
_route_cache: TTLCache = TTLCache(maxsize=1000, ttl=600)


def _route_to_stats(r: Route) -> RouteStats:
    return RouteStats(
        geometry=GeoJSONLineString(coordinates=r.geometry["coordinates"]),
        distance_m=r.distance_m,
        mean_pm25=r.mean_pm25,
        walk_seconds=r.walk_seconds,
        total_exposure=r.total_exposure,
    )


@router.post("/route", response_model=RouteResponse, tags=["route"])
def post_route(req: RouteRequest) -> RouteResponse:
    """Compare a length-only shortest path against a PM-weighted cleanest
    path between two DFW addresses. Both addresses are geocoded server-side
    via LocationIQ and snapped to the nearest node on the OSM walking graph.

    First call after a cold boot pays the OSMnx walking-graph load (set
    AERIA_PRELOAD_GRAPH=1 to amortize that at startup). Subsequent calls
    ride the in-process graph + 5-min grid cache and respond in <1s.
    """
    # Demo-mode short-circuit. The deployed free-tier instance can't host
    # the 569 MB walking graph, so this returns 503 with a structured
    # detail the frontend renders as a "preview only" banner. Local dev
    # leaves AERIA_ROUTING_ENABLED unset → the check passes and routing
    # works normally.
    if os.getenv("AERIA_ROUTING_ENABLED", "1") != "1":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "routing_disabled",
                "message": (
                    "Route Lab is preview-only in this deployment. "
                    "Run locally for live route comparison."
                ),
            },
        )

    try:
        snap = get_cached_snapshot()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Configuration error: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Pipeline failure: {e}")

    cache_key = (req.start.strip().lower(), req.end.strip().lower())
    cached = _route_cache.get(cache_key)
    if cached is not None and cached.timestamp == snap.timestamp:
        return cached

    try:
        result = find_routes(req.start, req.end, grid=snap)
    except GeocodeFailure as e:
        # Router messages already include the failing address (start or end).
        raise HTTPException(status_code=400, detail=f"Could not geocode address: {e}")
    except OutOfDFWError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Address resolves outside the DFW bounding box: {e}",
        )
    except DisconnectedRouteError:
        raise HTTPException(
            status_code=404,
            detail="No walking path exists between the two locations.",
        )
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Walking graph not yet loaded — try again in a moment.",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Routing pipeline failure: {e!r}")

    response = RouteResponse(
        cleanest=_route_to_stats(result.cleanest),
        shortest=_route_to_stats(result.shortest),
        timestamp=snap.timestamp,
    )
    _route_cache[cache_key] = response
    return response
