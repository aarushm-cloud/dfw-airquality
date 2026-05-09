from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """Body for POST /api/route — two human-readable addresses inside DFW.

    The geocoder runs server-side, so the API consumer doesn't need to know
    coordinates. `alpha` (the cleanest-route tuning knob in
    config.ROUTE_PM_ALPHA) is intentionally not exposed here — it's an
    internal weighting parameter, not a user-facing input.
    """

    start: str = Field(min_length=1, description="Start address (street, landmark, or neighborhood).")
    end: str = Field(min_length=1, description="End address (street, landmark, or neighborhood).")
