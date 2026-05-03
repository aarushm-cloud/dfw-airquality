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
