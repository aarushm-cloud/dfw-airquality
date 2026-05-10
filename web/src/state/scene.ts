import { create } from 'zustand';
import type * as THREE from 'three';

// Bridges the OrbitControls / camera handles inside the R3F <Canvas> into
// DOM-side code (e.g. zip-search → camera pan). Components outside the canvas
// can't read R3F refs directly; the store is the seam.
//
// CRITICAL: scene components must clear the handles on unmount, otherwise HMR
// or a scene remount can leave a stale OrbitControls instance pointing at a
// destroyed Three camera, which crashes the next pan.
//
// Note: THREE is type-only here. The snapshot is a plain-data tuple shape so
// nothing in this module touches a THREE constructor at runtime — that keeps
// `three` out of the main chunk even though several main-chunk modules import
// useSceneStore. Snapshot/restore mutate position/target via Vector3 instance
// methods (.toArray / .fromArray) on the live camera + controls handles.
type Vec3Tuple = [number, number, number];

type CameraSnapshot = {
  position: Vec3Tuple;
  target: Vec3Tuple;
  zoom: number;
};

type PanRequest = {
  worldX: number;
  worldZ: number;
  // Monotonic timestamp so identical-target requests still trigger a fresh
  // pan (e.g. user clicks the same cell twice). Without this, useEffect's
  // shallow compare on the request object would still re-fire because the
  // object identity changes — but the timestamp is what CityScene uses to
  // dedupe against the last applied request and stay idempotent across
  // StrictMode double-invokes.
  requestedAt: number;
};

type SceneState = {
  controls: any | null;
  camera: THREE.Camera | null;
  cityCameraSnapshot: CameraSnapshot | null;
  panRequest: PanRequest | null;
  registerControls: (controls: any | null, camera: THREE.Camera | null) => void;
  // City scene unmount calls snapshot before clearing the handles. City scene
  // mount calls restore synchronously after registerControls so the first
  // paint already shows the saved pose (no one-frame flash).
  snapshotCityCamera: () => void;
  restoreCityCamera: () => void;
  // Emitted by grid.ts on selection-with-pan. CityScene watches and calls
  // panCameraTo. Keeps cameraPan.ts (and its THREE import) out of grid.ts.
  requestPan: (worldX: number, worldZ: number) => void;
};

export const useSceneStore = create<SceneState>((set, get) => ({
  controls: null,
  camera: null,
  cityCameraSnapshot: null,
  panRequest: null,
  registerControls: (controls, camera) => set({ controls, camera }),
  snapshotCityCamera: () => {
    const { controls, camera } = get();
    if (!controls || !camera) return;
    set({
      cityCameraSnapshot: {
        position: camera.position.toArray() as Vec3Tuple,
        target: controls.target.toArray() as Vec3Tuple,
        zoom: (camera as any).zoom ?? 1,
      },
    });
  },
  restoreCityCamera: () => {
    const { controls, camera, cityCameraSnapshot } = get();
    if (!controls || !camera || !cityCameraSnapshot) return;
    camera.position.fromArray(cityCameraSnapshot.position);
    controls.target.fromArray(cityCameraSnapshot.target);
    if ((camera as any).zoom !== undefined) {
      (camera as any).zoom = cityCameraSnapshot.zoom;
      (camera as any).updateProjectionMatrix?.();
    }
    controls.update();
  },
  requestPan: (worldX, worldZ) =>
    set({ panRequest: { worldX, worldZ, requestedAt: Date.now() } }),
}));
