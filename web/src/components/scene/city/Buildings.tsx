import { useLayoutEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { generateBuildings } from '../../../world/city/buildings';

export function Buildings() {
  const buildings = useMemo(() => generateBuildings(), []);
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const tempObject = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    for (let i = 0; i < buildings.length; i++) {
      const b = buildings[i];
      tempObject.position.set(b.x, 0.01 + b.height / 2, b.z);
      tempObject.scale.set(b.width, b.height, b.depth);
      tempObject.updateMatrix();
      mesh.setMatrixAt(i, tempObject.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [buildings, tempObject]);

  // raycast={null} so clicks pass through to the cell underneath — cells own
  // the click target. frustumCulled={false} guards against an over-tight
  // bounding sphere dropping all instances in some camera positions.
  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, buildings.length]}
      raycast={() => null}
      frustumCulled={false}
    >
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial
        color="#7a7480"
        roughness={0.85}
        metalness={0}
        flatShading
      />
    </instancedMesh>
  );
}
