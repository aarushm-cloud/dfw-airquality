import * as THREE from 'three';

// Camera-pan animation. Preserves the current camera offset from controls.target
// so the angle/zoom feel is unchanged across the pan. Returns a cancel fn that
// can be called by a follow-up pan to abort an in-flight animation.
//
// CAVEAT: offset preservation here is Cartesian (`camera.position - target`).
// With the locked top-down camera that's mostly a vertical Y offset and works
// fine. After a future retune to an isometric camera, switch to spherical-
// relative offset preservation so pans don't drift the polar angle. Tracked in
// CONTRACT.md → Future cleanup.
export function panCameraTo(
  controls: any,
  camera: THREE.Camera,
  targetWorldPos: { x: number; z: number },
  durationMs = 600,
): () => void {
  const startTarget = controls.target.clone();
  const endTarget = new THREE.Vector3(targetWorldPos.x, 0, targetWorldPos.z);
  const offset = new THREE.Vector3().subVectors(camera.position, controls.target);

  const startTime = performance.now();
  let cancelled = false;

  function tick() {
    if (cancelled) return;
    const t = Math.min(1, (performance.now() - startTime) / durationMs);
    const eased = 1 - Math.pow(1 - t, 3);

    controls.target.lerpVectors(startTarget, endTarget, eased);
    camera.position.copy(controls.target).add(offset);
    controls.update();

    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  return () => {
    cancelled = true;
  };
}
