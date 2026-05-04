import { Canvas } from '@react-three/fiber';
import { SceneRoot } from './scene/SceneRoot';

// Inline `position: fixed; inset: 0` ensures the canvas fills the viewport
// even when the Tailwind classes are clobbered by a DevTools layout — without
// it the canvas falls back to its 300×150 HTML default.
export function Scene() {
  return (
    <Canvas
      className="pointer-events-auto"
      style={{ position: 'fixed', inset: 0, zIndex: 0 }}
      gl={{ antialias: true }}
    >
      <SceneRoot />
    </Canvas>
  );
}
