import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { DoubleSide } from 'three';
import { CellGrid } from './CellGrid';

export function SceneRoot() {
  return (
    <>
      <color attach="background" args={['#0a0a0f']} />
      <fog attach="fog" args={['#0a0a0f', 35, 90]} />

      <hemisphereLight args={['#2a2438', '#1a1a26', 0.35]} />
      <directionalLight position={[15, 20, 10]} color="#ffd166" intensity={0.4} />
      <ambientLight intensity={0.15} />

      <PerspectiveCamera makeDefault position={[13, 18, 22]} fov={45} near={0.1} far={500} />
      <OrbitControls
        target={[0, 0, 0]}
        enableDamping
        dampingFactor={0.08}
        minDistance={10}
        maxDistance={60}
        minPolarAngle={0.2}
        maxPolarAngle={Math.PI / 2.4}
        enablePan
        panSpeed={0.6}
      />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow={false}>
        <planeGeometry args={[50, 50]} />
        <meshStandardMaterial color="#0a0a0f" roughness={1} metalness={0} side={DoubleSide} />
      </mesh>

      <CellGrid />

      {import.meta.env.DEV && <axesHelper args={[5]} />}
    </>
  );
}
