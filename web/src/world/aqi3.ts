// Three-side AQI helpers, isolated from aqi.ts to keep `three` out of the
// main chunk. Anything importing this file pulls THREE; anything importing
// aqi.ts (constants, classifyPm25, label/color helpers) does not. Importers
// of threeColorForPm25 must live inside the lazy Scene chunk.

import * as THREE from 'three';
import { AQI_COLOR, classifyPm25 } from './aqi';

// Cached: constructing THREE.Color from a hex string is non-trivial and the
// scene calls this 5,000+ times per data refresh. Six categories → six entries.
const _colorCache = new Map<string, THREE.Color>();
export function threeColorForPm25(pm25: number): THREE.Color {
  const hex = AQI_COLOR[classifyPm25(pm25)];
  let c = _colorCache.get(hex);
  if (!c) {
    c = new THREE.Color(hex);
    _colorCache.set(hex, c);
  }
  return c;
}
