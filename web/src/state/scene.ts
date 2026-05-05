import { create } from 'zustand';
import * as THREE from 'three';

// Bridges the OrbitControls / camera handles inside the R3F <Canvas> into
// DOM-side code (e.g. zip-search → camera pan). Components outside the canvas
// can't read R3F refs directly; the store is the seam.
//
// CRITICAL: scene components must clear the handles on unmount, otherwise HMR
// or a scene remount can leave a stale OrbitControls instance pointing at a
// destroyed Three camera, which crashes the next pan.
type CameraSnapshot = {
  position: THREE.Vector3;
  target: THREE.Vector3;
  zoom: number;
};

type SceneState = {
  controls: any | null;
  camera: THREE.Camera | null;
  cityCameraSnapshot: CameraSnapshot | null;
  registerControls: (controls: any | null, camera: THREE.Camera | null) => void;
  // City scene unmount calls snapshot before clearing the handles. City scene
  // mount calls restore synchronously after registerControls so the first
  // paint already shows the saved pose (no one-frame flash).
  snapshotCityCamera: () => void;
  restoreCityCamera: () => void;
};

export const useSceneStore = create<SceneState>((set, get) => ({
  controls: null,
  camera: null,
  cityCameraSnapshot: null,
  registerControls: (controls, camera) => set({ controls, camera }),
  snapshotCityCamera: () => {
    const { controls, camera } = get();
    if (!controls || !camera) return;
    set({
      cityCameraSnapshot: {
        position: camera.position.clone(),
        target: controls.target.clone(),
        zoom: (camera as any).zoom ?? 1,
      },
    });
  },
  restoreCityCamera: () => {
    const { controls, camera, cityCameraSnapshot } = get();
    if (!controls || !camera || !cityCameraSnapshot) return;
    camera.position.copy(cityCameraSnapshot.position);
    controls.target.copy(cityCameraSnapshot.target);
    if ((camera as any).zoom !== undefined) {
      (camera as any).zoom = cityCameraSnapshot.zoom;
      (camera as any).updateProjectionMatrix?.();
    }
    controls.update();
  },
}));
