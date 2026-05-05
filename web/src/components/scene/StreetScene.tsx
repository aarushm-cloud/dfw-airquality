import { useEffect, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Text } from '@react-three/drei';
import { useGrid, useSelectedCellMeta } from '../../state/grid';
import { useSceneStore } from '../../state/scene';

// Placeholder void: no ground plane, no buildings, no procedural geometry.
// Session 6 owns scene atmosphere. The void style is intentional placeholder
// messaging — a ground plane would read as "scene missing buildings".
export function StreetScene() {
  const controlsRef = useRef<any>(null);
  const { camera } = useThree();
  const registerControls = useSceneStore((s) => s.registerControls);
  const row = useGrid((s) => s.selectedCellRow);
  const col = useGrid((s) => s.selectedCellCol);
  const meta = useSelectedCellMeta();

  // Register/unregister with scene store. No snapshot/restore — every street
  // entry resets to the fixed pose configured below.
  useEffect(() => {
    if (!controlsRef.current) return;
    registerControls(controlsRef.current, camera);
    return () => registerControls(null, null);
  }, [camera, registerControls]);

  const hasCell = row !== null && col !== null;
  const zip = meta?.zip ?? null;
  const subtitle = hasCell
    ? `Cell ${row}·${col}${zip ? ` · ZIP ${zip}` : ''}`
    : null;

  return (
    <>
      <hemisphereLight args={['#3d3550', '#1a1a26', 0.4]} />
      <ambientLight intensity={0.4} />

      <PerspectiveCamera makeDefault position={[0, 1.6, 5]} fov={60} near={0.05} far={500} />
      <OrbitControls
        ref={controlsRef}
        target={[0, 1.6, 0]}
        enableZoom={false}
        enablePan={false}
        minPolarAngle={Math.PI / 3}
        maxPolarAngle={(2 * Math.PI) / 3}
      />

      <Text
        position={[0, 1.9, 0]}
        fontSize={0.18}
        color="#e7e5e4"
        anchorX="center"
        anchorY="middle"
        letterSpacing={0.1}
      >
        STREET VIEW PLACEHOLDER
      </Text>
      {subtitle && (
        <Text
          position={[0, 1.55, 0]}
          fontSize={0.11}
          color="#a8a29e"
          anchorX="center"
          anchorY="middle"
          letterSpacing={0.06}
        >
          {subtitle}
        </Text>
      )}
    </>
  );
}
