import { useEffect, useMemo, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { Instance, Instances, OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { useSceneStore } from '../../state/scene';
import { generateStreetBuildings } from '../../world/streetBuildings';
import { StreetParticles } from './StreetParticles';

// First-person dusk street. Stylized grey rectangles flank a Z-aligned street
// running through the camera. Lighting, buildings, and camera are AQI-agnostic
// — only the particle layer (Part B) reacts to cell selection.
export function StreetScene() {
  const controlsRef = useRef<any>(null);
  const { camera } = useThree();
  const registerControls = useSceneStore((s) => s.registerControls);

  // No snapshot/restore — every street entry resets to the fixed pose below.
  useEffect(() => {
    if (!controlsRef.current) return;
    registerControls(controlsRef.current, camera);
    return () => registerControls(null, null);
  }, [camera, registerControls]);

  const buildings = useMemo(() => generateStreetBuildings(), []);

  return (
    <>
      {/* Dusk fog overrides SceneRoot's city-distance fog while StreetScene is
          mounted; R3F's attach mechanism restores the previous fog on unmount. */}
      <fog attach="fog" args={['#0a0a0f', 10, 48]} />

      {/* Low warm sun, gold-orange. ACES tone mapping desaturates this slightly,
          so the source hex is more saturated than the perceived dusk gold. */}
      <directionalLight position={[12, 6, -8]} color="#ffb066" intensity={1.1} />
      {/* Magenta-leaning sky / warmer ground for the "deep blue bleeding into
          magenta haze" target from DESIGN_NOTES. Low intensity — fill, not key. */}
      <hemisphereLight args={['#5a3f6e', '#2a2230', 0.55]} />
      <ambientLight color="#2a2438" intensity={0.18} />

      <PerspectiveCamera makeDefault position={[0, 1.6, 5]} fov={62} near={0.05} far={200} />
      <OrbitControls
        ref={controlsRef}
        target={[0, 1.8, 0]}
        enableZoom={false}
        enablePan={false}
        minPolarAngle={Math.PI / 4}
        maxPolarAngle={(2.4 * Math.PI) / 4}
        rotateSpeed={0.4}
      />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[200, 200]} />
        <meshStandardMaterial color="#0c0b13" roughness={1} metalness={0} />
      </mesh>

      {/* Drei Instances is correct for the static building set: count is fixed
          at mount, so the component-driven API fits cleanly. (Particles use
          raw <instancedMesh> because their count mutates per AQI change.) */}
      <Instances limit={buildings.length} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.92} metalness={0} flatShading />
        {buildings.map((b, i) => {
          const r = Math.round(122 * b.shade);
          const g = Math.round(116 * b.shade);
          const bl = Math.round(128 * b.shade);
          return (
            <Instance
              key={i}
              position={[b.x, b.y, b.z]}
              scale={[b.width, b.height, b.depth]}
              color={`rgb(${r}, ${g}, ${bl})`}
            />
          );
        })}
      </Instances>

      <StreetParticles />
    </>
  );
}
