import logging

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
    try:
        snap = get_cached_snapshot()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Configuration error: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Pipeline failure: {e}")

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

    return RouteResponse(
        cleanest=_route_to_stats(result.cleanest),
        shortest=_route_to_stats(result.shortest),
        timestamp=snap.timestamp,
    )
