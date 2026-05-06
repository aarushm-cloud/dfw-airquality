import { useLayoutEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useGrid } from '../../../state/grid';
import { CELL_X, CELL_Z, GRID_SIZE, cellToWorld } from '../../../world/bbox';
import { threeColorForPm25 } from '../../../world/aqi';

const FLOOR_BASE_ALPHA = 0.5;
const TOTAL_INSTANCES = GRID_SIZE * GRID_SIZE;

export function CellFloorTint() {
  const cells = useGrid((s) => s.cells);
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const tempObject = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh || cells.length === 0) return;

    // Explicit instanceColor allocation. Three.js doesn't always auto-allocate
    // before setColorAt — without this, all instances render in the material's
    // default color (white).
    if (!mesh.instanceColor) {
      mesh.instanceColor = new THREE.InstancedBufferAttribute(
        new Float32Array(TOTAL_INSTANCES * 3),
        3,
      );
    }

    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i];
      const { x, z } = cellToWorld({ row: cell.row, col: cell.col });

      tempObject.position.set(x, 0.005, z);
      tempObject.rotation.set(-Math.PI / 2, 0, 0);
      tempObject.scale.set(CELL_X * 0.96, CELL_Z * 0.96, 1);
      tempObject.updateMatrix();
      mesh.setMatrixAt(i, tempObject.matrix);

      // Premultiplied-alpha trick: the material's opacity is fixed at
      // FLOOR_BASE_ALPHA, so we encode confidence into RGB by multiplying
      // by (confAlpha / FLOOR_BASE_ALPHA). Caveat: low-confidence cells fade
      // toward black, not toward transparent. The Session 5 LOW CONFIDENCE
      // text flag carries the actual signal; floor tint is corroborating.
      const baseColor = threeColorForPm25(cell.pm25Mean).clone();
      const conf = Math.max(0, Math.min(1, cell.confidenceMin));
      const confAlpha = 0.05 + Math.pow(conf, 2) * 0.35;
      const factor = confAlpha / FLOOR_BASE_ALPHA;
      baseColor.multiplyScalar(factor);
      mesh.setColorAt(i, baseColor);
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [cells, tempObject]);

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, TOTAL_INSTANCES]}
      raycast={() => null}
      castShadow={false}
      receiveShadow={false}
    >
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial
        transparent
        opacity={FLOOR_BASE_ALPHA}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </instancedMesh>
  );
}
