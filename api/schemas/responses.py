from typing import Literal

from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    sensor_id: str
    name: str
    lat: float
    lon: float
    pm25: float
    pm25_raw: float | None = None
    epa_corrected: int
    source: str


class SensorsResponse(BaseModel):
    count: int
    timestamp: str
    sensors: list[SensorReading]


class BBox(BaseModel):
    north: float
    south: float
    east: float
    west: float


class GridResponse(BaseModel):
    timestamp: str
    resolution: int = Field(description="Grid is resolution x resolution")
    bbox: BBox
    lats: list[float] = Field(description="1D array of latitudes, length = resolution")
    lons: list[float] = Field(description="1D array of longitudes, length = resolution")
    pm25: list[list[float]] = Field(description="2D PM2.5 grid, shape [resolution][resolution], row-major lat-major")
    confidence: list[list[float]] = Field(description="2D confidence grid, same shape as pm25, values in [0, 1]")
    wind_speed: float
    wind_deg: float
    sensor_count: int
    avg_pm25: float


class CellResponse(BaseModel):
    zip: str
    lat: float
    lon: float
    cell_lat: float
    cell_lon: float
    cell_i: int
    cell_j: int
    pm25: float
    aqi_category: str
    confidence: float
    neighborhood: str | None = None
    timestamp: str


class CellAtResponse(BaseModel):
    lat: float
    lon: float
    zip: str | None
    neighborhood: str | None
    row: int | None
    col: int | None
    in_bbox: bool


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(description="Polyline as [[lon, lat], ...]")


class RouteStats(BaseModel):
    geometry: GeoJSONLineString
    distance_m: float
    mean_pm25: float = Field(description="Exposure-weighted mean PM2.5 along the path (µg/m³)")
    walk_seconds: float = Field(description="Walk time at 1.4 m/s")
    total_exposure: float = Field(description="Σ pm_midpoint × edge_length (µg/m³·m)")


class RouteResponse(BaseModel):
    cleanest: RouteStats
    shortest: RouteStats
    timestamp: str = Field(description="PipelineSnapshot timestamp the route was computed against")
