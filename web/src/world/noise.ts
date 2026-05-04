import { createNoise2D } from 'simplex-noise';

// LCG seeded so the city is stable across reloads. Don't change this seed
// without a reason — it'll redraw the entire skyline.
const PRNG = (seed: number) => {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x100000000;
  };
};

export const noise2D = createNoise2D(PRNG(0xae12a));

export function noise01(x: number, y: number): number {
  return (noise2D(x, y) + 1) / 2;
}
