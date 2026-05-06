// Deterministic procedural placement of stylized grey rectangles along two
// rows on either side of a street running through the camera Z axis.
// Buildings are scene furniture, not data — same buildings every mount, every
// cell change. Particles do the AQI work; buildings stay constant.

function mulberry32(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type StreetBuilding = {
  x: number;
  y: number;
  z: number;
  width: number;
  height: number;
  depth: number;
  shade: number;
};

const STREET_HALF_WIDTH = 6;
const SIDEWALK_TO_FACADE = 1.5;

// Two segments with a vista buffer in between so the camera (at z=+5) gets a
// clear sightline down the street instead of a building slab in its face.
// Camera can rotate full horizontal so we keep a few buildings behind it too.
const SEGMENTS = [
  { start: 12, end: 8 },
  { start: -4, end: -56 },
];

export function generateStreetBuildings(): StreetBuilding[] {
  const rand = mulberry32(42);
  const out: StreetBuilding[] = [];

  for (const side of [-1, 1] as const) {
    for (const seg of SEGMENTS) {
      let z = seg.start;
      while (z > seg.end) {
        const width = 3 + rand() * 5;
        const depth = 1.8 + rand() * 2.6;
        const height = 4 + rand() * 14;
        const shade = 0.78 + rand() * 0.34;

        const offset = STREET_HALF_WIDTH + SIDEWALK_TO_FACADE + (rand() - 0.5) * 1.2;
        const x = side * (offset + width / 2);
        const y = height / 2;

        out.push({ x, y, z: z - depth / 2, width, height, depth, shade });

        const gap = 0.3 + rand() * 1.0;
        z -= depth + gap;
      }
    }
  }

  return out;
}

if (import.meta.env.DEV) {
  const all = generateStreetBuildings();
  console.assert(
    all.length >= 30 && all.length <= 80,
    `[streetBuildings] expected 30-80 buildings, got ${all.length}`,
  );
}
