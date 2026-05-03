// Coordinate-system source of truth for the AERIA city scene.
//
// World-space conventions (right-handed, Y-up — R3F default):
//   X: east is +X, west is -X       (longitude direction)
//   Z: north is -Z, south is +Z     (top-down camera view reads "north up")
//   Y: vertical, ground at Y=0      (cells render at Y=0.01 to avoid z-fighting)
//
// Cell-grid storage:
//   row 0   = southernmost   col 0  = westernmost
//   row 29  = northernmost   col 29 = easternmost
//   indexed row-major, i = row * GRID_SIZE + col
//
// The source /api/grid array uses pm25[latIdx][lonIdx] with lats[0]=south,
// lons[0]=west, so row→latIdx and col→lonIdx with no flip.
//
// Cosine correction: at Dallas's latitude (~32.78°N), 1° of longitude is only
// ~0.840° of "physical-distance equivalent latitude". Applying this
// correction matches the rest of the project (engine/interpolation.py et al.)
// and keeps the visual grid consistent with the underlying physics. As a
// consequence, world-space cells are slightly rectangular (~0.935 × 1.0) but
// each cell still represents the same ground area.

export const BBOX = {
  west: -97.05,
  east: -96.46,
  south: 32.55,
  north: 33.08,
} as const;

export const GRID_SIZE = 30;
export const SOURCE_GRID_SIZE = 200;

export const REF_LAT_DEG = 32.78;
export const LON_CORRECTION = Math.cos((REF_LAT_DEG * Math.PI) / 180);

const LON_SPAN_CORRECTED = (BBOX.east - BBOX.west) * LON_CORRECTION;
const LAT_SPAN = BBOX.north - BBOX.south;

export const WORLD_PER_DEG = 30 / Math.max(LON_SPAN_CORRECTED, LAT_SPAN);

export const WORLD_HALF_X = (LON_SPAN_CORRECTED * WORLD_PER_DEG) / 2;
export const WORLD_HALF_Z = (LAT_SPAN * WORLD_PER_DEG) / 2;

export const CELL_X = (WORLD_HALF_X * 2) / GRID_SIZE;
export const CELL_Z = (WORLD_HALF_Z * 2) / GRID_SIZE;

export type CellCoord = { row: number; col: number };
export type LatLon = { lat: number; lon: number };
export type WorldXZ = { x: number; z: number };

export function cellToLatLon({ row, col }: CellCoord): LatLon {
  const lat = BBOX.south + ((row + 0.5) * (BBOX.north - BBOX.south)) / GRID_SIZE;
  const lon = BBOX.west + ((col + 0.5) * (BBOX.east - BBOX.west)) / GRID_SIZE;
  return { lat, lon };
}

export function latLonToWorld({ lat, lon }: LatLon): WorldXZ {
  const lonOffset = (lon - (BBOX.west + BBOX.east) / 2) * LON_CORRECTION;
  const latOffset = lat - (BBOX.south + BBOX.north) / 2;
  return {
    x: lonOffset * WORLD_PER_DEG,
    z: -latOffset * WORLD_PER_DEG,
  };
}

export function cellToWorld(c: CellCoord): WorldXZ {
  return latLonToWorld(cellToLatLon(c));
}

export function latLonToCell({ lat, lon }: LatLon): CellCoord | null {
  if (lat < BBOX.south || lat >= BBOX.north) return null;
  if (lon < BBOX.west || lon >= BBOX.east) return null;
  const row = Math.floor(((lat - BBOX.south) * GRID_SIZE) / (BBOX.north - BBOX.south));
  const col = Math.floor(((lon - BBOX.west) * GRID_SIZE) / (BBOX.east - BBOX.west));
  return { row, col };
}

if (import.meta.env.DEV) {
  const samples: CellCoord[] = [
    { row: 0, col: 0 },
    { row: 0, col: 29 },
    { row: 29, col: 0 },
    { row: 29, col: 29 },
    { row: 15, col: 15 },
  ];
  for (const c of samples) {
    const back = latLonToCell(cellToLatLon(c));
    console.assert(
      back?.row === c.row && back?.col === c.col,
      `[bbox] round-trip failed for ${JSON.stringify(c)} → ${JSON.stringify(back)}`,
    );
  }
}
