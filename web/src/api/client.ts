const FALLBACK_BASE_URL = 'http://localhost:8000';
const configured = import.meta.env.VITE_API_BASE_URL;
const BASE_URL = configured ?? FALLBACK_BASE_URL;

console.info(`[api] base URL: ${BASE_URL}${configured ? '' : ' (fallback)'}`);

export type Health = {
  status: string;
  cache_warm: boolean;
  uptime_seconds: number;
};

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${BASE_URL}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export type GridResponse = {
  lats: number[];
  lons: number[];
  pm25: number[][];
  confidence: number[][];
  generated_at?: string;
  timestamp?: string;
};

export async function getGrid(): Promise<GridResponse> {
  const res = await fetch(`${BASE_URL}/api/grid`);
  if (!res.ok) throw new Error(`Grid fetch failed: ${res.status}`);
  return res.json();
}

// Mirrors api/schemas/responses.py::CellResponse exactly. cell_i/cell_j are
// indices into the 200×200 source grid, NOT the 30×30 cell grid the scene
// renders — the frontend re-derives 30×30 row/col via latLonToCell(lat, lon).
export type CellByZip = {
  zip: string;
  lat: number;
  lon: number;
  cell_lat: number;
  cell_lon: number;
  cell_i: number;
  cell_j: number;
  pm25: number;
  aqi_category: string;
  confidence: number;
  neighborhood: string | null;
  timestamp: string;
};

// Mirrors api/schemas/responses.py::CellAtResponse.
export type CellAt = {
  lat: number;
  lon: number;
  zip: string | null;
  neighborhood: string | null;
  row: number | null;
  col: number | null;
  in_bbox: boolean;
};

export class ZipNotCoveredError extends Error {
  constructor(public zip: string) {
    super(`Zip ${zip} is not in coverage area`);
    this.name = 'ZipNotCoveredError';
  }
}

export async function getCellByZip(zip: string): Promise<CellByZip> {
  const res = await fetch(`${BASE_URL}/api/cells/${zip}`);
  if (res.status === 404) throw new ZipNotCoveredError(zip);
  if (!res.ok) throw new Error(`Cell lookup failed: ${res.status}`);
  return res.json();
}

export async function getCellAt(lat: number, lon: number): Promise<CellAt> {
  const url = new URL(`${BASE_URL}/api/cells/at`);
  url.searchParams.set('lat', String(lat));
  url.searchParams.set('lon', String(lon));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Coord lookup failed: ${res.status}`);
  return res.json();
}

// /api/sensors shape (verified via curl 2026-05-04):
// { count: number, timestamp: string, sensors: SensorRow[] }
// No wind fields exposed at metro or per-sensor level — see CONTRACT future-cleanup.
export type SensorsResponse = {
  count: number;
  timestamp: string;
  sensors: Array<{
    sensor_id: string;
    name: string;
    lat: number;
    lon: number;
    pm25: number;
    pm25_raw: number;
    epa_corrected: number;
    source: string;
  }>;
};

export async function getSensors(): Promise<SensorsResponse> {
  const res = await fetch(`${BASE_URL}/api/sensors`);
  if (!res.ok) throw new Error(`Sensors fetch failed: ${res.status}`);
  return res.json();
}

// Mirrors api/schemas/responses.py::GeocodeSuggestion exactly.
export type GeocodeSuggestion = {
  display_name: string;
  lat: number;
  lon: number;
};

export async function getGeocodeSuggestions(
  q: string,
  limit = 5,
  signal?: AbortSignal,
): Promise<GeocodeSuggestion[]> {
  const url = new URL(`${BASE_URL}/api/geocode/suggest`);
  url.searchParams.set('q', q);
  url.searchParams.set('limit', String(limit));
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Geocode suggest failed: ${res.status}`);
  return res.json();
}

// Mirrors api/schemas/{requests,responses}.py for POST /api/route.
export type RouteRequest = { start: string; end: string };

export type GeoJSONLineString = {
  type: 'LineString';
  coordinates: [number, number][]; // [lon, lat], GeoJSON convention
};

export type RouteStats = {
  geometry: GeoJSONLineString;
  distance_m: number;
  mean_pm25: number;
  walk_seconds: number;
  total_exposure: number;
};

export type RouteResponse = {
  cleanest: RouteStats;
  shortest: RouteStats;
  timestamp: string;
};

// Carries the backend-mapped status code and detail body so callers can
// distinguish 400/404/422/502/503 without re-parsing the body. Mirrors the
// ZipNotCoveredError pattern. `detail` stays loosely-typed because FastAPI's
// HTTPException allows either a string or a structured dict — the routing-
// disabled demo case ships {code, message}, while every other error path
// stays a plain string.
export class RouteApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
    this.name = 'RouteApiError';
  }
}

export async function postRoute(req: RouteRequest): Promise<RouteResponse> {
  const res = await fetch(`${BASE_URL}/api/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let detail: unknown = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail !== undefined) detail = body.detail;
    } catch {
      // body wasn't JSON — keep the generic detail
    }
    throw new RouteApiError(res.status, detail);
  }
  return res.json();
}
