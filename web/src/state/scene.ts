import { create } from 'zustand';
import * as THREE from 'three';

// Bridges the OrbitControls / camera handles inside the R3F <Canvas> into
// DOM-side code (e.g. zip-search → camera pan). Components outside the canvas
// can't read R3F refs directly; the store is the seam.
//
// CRITICAL: SceneRoot must clear the handles on unmount, otherwise HMR or a
// scene remount can leave a stale OrbitControls instance pointing at a
// destroyed Three camera, which crashes the next pan.
type SceneState = {
  controls: any | null;
  camera: THREE.Camera | null;
  registerControls: (controls: any | null, camera: THREE.Camera | null) => void;
};

export const useSceneStore = create<SceneState>((set) => ({
  controls: null,
  camera: null,
  registerControls: (controls, camera) => set({ controls, camera }),
}));
