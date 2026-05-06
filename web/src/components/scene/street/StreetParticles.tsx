import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useSelectedCell, useSelectedCategory } from '../../../state/grid';
import { AQI_COLOR } from '../../../world/aqi';

// Allocate-once / set-count-dynamically (Option A in the session prompt). We
// pre-allocate MAX_PARTICLES instance slots up front, then mutate mesh.count
// per AQI change. Three.js's renderer respects mesh.count and only draws that
// many — no allocation churn, no pop on cell change. Per CONTRACT, particles
// use raw <instancedMesh> (not Drei <Instances>) because count mutates.
const MAX_PARTICLES = 3000;
const RADIUS_XZ = 13;
const Y_MIN = 0.4;
const Y_MAX = 3.2;

// Density curve documented in CONTRACT: count = clamp(50 + pm25 * 30, 50, 3000).
// Good (pm25 ~ 8) → ~290; Moderate (~25) → ~800; Sensitive (~45) → ~1400;
// Unhealthy (~100) → 3000 (cap); Very Unhealthy / Hazardous → cap.
function particleCount(pm25: number): number {
  if (!isFinite(pm25)) return 0;
  return Math.min(MAX_PARTICLES, Math.max(50, Math.round(50 + pm25 * 30)));
}

export function StreetParticles() {
  const cell = useSelectedCell();
  const category = useSelectedCategory();
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const tempObject = useMemo(() => new THREE.Object3D(), []);

  // Per-particle seed, generated once: base position (anchored in world space
  // around the street centre, NOT around the moving camera — atmospheric haze
  // the user looks through), drift phase, drift speed.
  const seeds = useMemo(() => {
    const arr = new Float32Array(MAX_PARTICLES * 5);
    for (let i = 0; i < MAX_PARTICLES; i++) {
      const angle = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * RADIUS_XZ;
      arr[i * 5 + 0] = Math.cos(angle) * r;
      arr[i * 5 + 1] = Y_MIN + Math.random() * (Y_MAX - Y_MIN);
      arr[i * 5 + 2] = Math.sin(angle) * r;
      arr[i * 5 + 3] = Math.random() * Math.PI * 2;
      arr[i * 5 + 4] = 0.4 + Math.random() * 0.7;
    }
    return arr;
  }, []);

  const count = cell ? particleCount(cell.pm25Mean) : 0;

  const aqiColor = useMemo(
    () => (category ? new THREE.Color(AQI_COLOR[category]) : new THREE.Color('#ffffff')),
    [category],
  );

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    mesh.count = count;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const mat = mesh.material as THREE.MeshBasicMaterial;
    mat.color.copy(aqiColor);
  }, [count, aqiColor]);

  // useFrame is the R3F per-frame hook. We update each visible instance's
  // position with sinusoidal drift; mesh.instanceMatrix.needsUpdate = true
  // tells three.js the buffer changed.
  useFrame((state) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const c = mesh.count;
    if (c === 0) return;
    const t = state.clock.getElapsedTime();

    for (let i = 0; i < c; i++) {
      const px = seeds[i * 5 + 0];
      const py = seeds[i * 5 + 1];
      const pz = seeds[i * 5 + 2];
      const phase = seeds[i * 5 + 3];
      const speed = seeds[i * 5 + 4];

      const driftY = Math.sin(t * 0.35 * speed + phase) * 0.18;
      const driftX = Math.cos(t * 0.28 * speed + phase * 1.3) * 0.12;
      const driftZ = Math.sin(t * 0.22 * speed + phase * 0.7) * 0.12;

      tempObject.position.set(px + driftX, py + driftY, pz + driftZ);
      tempObject.scale.setScalar(0.075);
      tempObject.updateMatrix();
      mesh.setMatrixAt(i, tempObject.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, MAX_PARTICLES]}
      raycast={() => null}
      frustumCulled={false}
      castShadow={false}
      receiveShadow={false}
    >
      <sphereGeometry args={[1, 6, 4]} />
      <meshBasicMaterial transparent opacity={0.78} depthWrite={false} />
    </instancedMesh>
  );
}
