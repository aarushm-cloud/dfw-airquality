import { CELL_X, CELL_Z, GRID_SIZE, cellToWorld } from '../bbox';
import { noise01, noise2D } from '../noise';

export type Building = {
  x: number;
  z: number;
  width: number;
  depth: number;
  height: number;
  row: number;
  col: number;
};

const RADIAL_FALLOFF = 6.5;

function densityAtCell(row: number, col: number): number {
  const { x, z } = cellToWorld({ row, col });
  const radial = Math.exp(-Math.hypot(x, z) / RADIAL_FALLOFF);
  const local = noise01(row * 0.35, col * 0.35);
  // Low-frequency separation noise carves "valleys" between dense regions so
  // the metro reads as multiple distinct cities rather than one continuous
  // blob. Range [0.4, 1.0] keeps suburbs sparse but not totally dead.
  const separation = 0.4 + 0.6 * noise01(row * 0.08, col * 0.08);
  return (radial * 0.7 + local * 0.3 + radial * local * 0.4) * separation;
}

function buildingCountForDensity(d: number): number {
  if (d < 0.18) return 0;
  if (d < 0.4) return 1;
  if (d < 0.7) return 2;
  return 3;
}

export function generateBuildings(): Building[] {
  const out: Building[] = [];

  for (let row = 0; row < GRID_SIZE; row++) {
    for (let col = 0; col < GRID_SIZE; col++) {
      const density = densityAtCell(row, col);
      const count = buildingCountForDensity(density);
      if (count === 0) continue;

      const center = cellToWorld({ row, col });

      for (let b = 0; b < count; b++) {
        const baseHeight = 0.3 + density * 1.8;
        const heightNoise = noise01(row * 0.7 + b * 1.3, col * 0.7 + b * 0.9);
        const height = Math.max(0.2, baseHeight * (0.7 + 0.6 * heightNoise));

        const footprintFrac = 0.32 + 0.23 * (1 - Math.min(height, 2.5) / 2.5);
        const width = footprintFrac * CELL_X;
        const depth = footprintFrac * CELL_Z;

        const maxOffsetX = (CELL_X - width) / 2 - 0.02;
        const maxOffsetZ = (CELL_Z - depth) / 2 - 0.02;
        const offsetX = noise2D(row * 1.7 + b, col * 1.7) * maxOffsetX;
        const offsetZ = noise2D(row * 1.7, col * 1.7 + b) * maxOffsetZ;

        out.push({
          x: center.x + offsetX,
          z: center.z + offsetZ,
          width,
          depth,
          height,
          row,
          col,
        });
      }
    }
  }

  return out;
}

if (import.meta.env.DEV) {
  const all = generateBuildings();
  console.assert(
    all.length >= 400 && all.length <= 1500,
    `[buildings] expected 400–1500 buildings, got ${all.length}`,
  );
}
