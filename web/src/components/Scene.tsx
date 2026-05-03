import { Canvas } from '@react-three/fiber';

export function Scene() {
  return (
    <Canvas
      className="fixed inset-0 z-0 pointer-events-none"
      camera={{ position: [0, 8, 14], fov: 50, near: 0.1, far: 1000 }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={['#0a0a0f']} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[5, 10, 5]} intensity={0.6} />
    </Canvas>
  );
}
