import { Canvas } from '@react-three/fiber';
import { SceneRoot } from './scene/SceneRoot';

export function Scene() {
  return (
    <Canvas
      className="fixed inset-0 z-0 pointer-events-auto"
      gl={{ antialias: true }}
    >
      <SceneRoot />
    </Canvas>
  );
}
