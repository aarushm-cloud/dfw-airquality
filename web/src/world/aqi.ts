// PM₂.₅ → AQI category mapping. Mirrors AQI_THRESHOLDS in config.py and the
// PM25_COLORSCALE in viz/heatmap.py. The colors here are the only place AQI
// hues are allowed in DOM chrome (the dot literally restates the AQI signal).

import * as THREE from 'three';

export type AqiCategory =
  | 'good'
  | 'moderate'
  | 'sensitive'
  | 'unhealthy'
  | 'veryUnhealthy'
  | 'hazardous';

export const AQI_LABEL: Record<AqiCategory, string> = {
  good: 'GOOD',
  moderate: 'MODERATE',
  sensitive: 'SENSITIVE',
  unhealthy: 'UNHEALTHY',
  veryUnhealthy: 'VERY UNHEALTHY',
  hazardous: 'HAZARDOUS',
};

export const AQI_COLOR: Record<AqiCategory, string> = {
  good: '#00e400',
  moderate: '#ffff00',
  sensitive: '#ff7e00',
  unhealthy: '#ff0000',
  veryUnhealthy: '#8f3f97',
  hazardous: '#7e0023',
};

export function classifyPm25(pm25: number): AqiCategory {
  if (pm25 <= 12) return 'good';
  if (pm25 <= 35.4) return 'moderate';
  if (pm25 <= 55.4) return 'sensitive';
  if (pm25 <= 150.4) return 'unhealthy';
  if (pm25 <= 250.4) return 'veryUnhealthy';
  return 'hazardous';
}

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

export const LOW_CONFIDENCE_THRESHOLD = 0.4;

export type ConfidenceLabel = 'high' | 'moderate' | 'low';

export function confidenceLabel(conf: number): ConfidenceLabel {
  if (conf >= 0.7) return 'high';
  if (conf >= LOW_CONFIDENCE_THRESHOLD) return 'moderate';
  return 'low';
}
