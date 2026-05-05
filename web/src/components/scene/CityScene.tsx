import { useEffect, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { Buildings } from './Buildings';
import { CellFloorTint } from './CellFloorTint';
import { CellGrid } from './CellGrid';
import { Particles } from './Particles';
import { useSceneStore } from '../../state/scene';

export function CityScene() {
  const controlsRef = useRef<any>(null);
  const { camera } = useThree();
  const registerControls = useSceneStore((s) => s.registerControls);

  // Publish handles for DOM-side panners. On mount, restore any previously
  // captured snapshot synchronously so the first paint is at the saved pose
  // (avoids a one-frame flash). The snapshot itself is captured by
  // useViewStore.setView at the city→street transition boundary — NOT here
  // on unmount — so React StrictMode's effect double-invoke can't cache the
  // R3F default camera before <PerspectiveCamera makeDefault> takes effect.
  useEffect(() => {
    if (!controlsRef.current) return;
    registerControls(controlsRef.current, camera);
    if (useSceneStore.getState().cityCameraSnapshot) {
      useSceneStore.getState().restoreCityCamera();
    }
    return () => registerControls(null, null);
  }, [camera, registerControls]);

  return (
    <>
      <hemisphereLight args={['#3d3550', '#1a1a26', 0.7]} />
      <directionalLight position={[15, 20, 10]} color="#ffd166" intensity={0.3} />
      <ambientLight intensity={0.3} />

      {/* Initial framing is top-down at Y=38 so the whole 28×30 grid fills
          ~93% of a 16:9 viewport. The tiny Z offset (0.1) gives OrbitControls
          a defined "up" direction so the user can rotate away from top-down
          without hitting the polar singularity. */}
      <PerspectiveCamera makeDefault position={[0, 38, 0.1]} fov={45} near={0.1} far={500} />
      <OrbitControls
        ref={controlsRef}
        target={[0, 0, 0]}
        enableDamping
        dampingFactor={0.18}
        minDistance={4}
        maxDistance={60}
        minPolarAngle={0}
        maxPolarAngle={Math.PI / 2.4}
        enablePan={false}
        rotateSpeed={0.5}
        zoomSpeed={0.7}
      />

      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[50, 50]} />
        <meshStandardMaterial color="#0a0a0f" roughness={1} />
      </mesh>

      <CellFloorTint />
      <CellGrid />
      <Buildings />
      <Particles />

      {import.meta.env.DEV && <axesHelper args={[5]} />}
    </>
  );
}
