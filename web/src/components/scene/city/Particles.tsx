import { useLayoutEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useGrid } from '../../../state/grid';
import { CELL_X, CELL_Z, cellToWorld } from '../../../world/bbox';
import { threeColorForPm25 } from '../../../world/aqi';

function particleCountForPm25(pm25: number): number {
  if (pm25 < 12) return Math.floor(1 + Math.random() * 2);
  if (pm25 < 35) return Math.floor(3 + Math.random() * 3);
  if (pm25 < 55) return Math.floor(6 + Math.random() * 4);
  if (pm25 < 150) return Math.floor(10 + Math.random() * 5);
  if (pm25 < 250) return Math.floor(15 + Math.random() * 5);
  return Math.floor(20 + Math.random() * 5);
}

export function Particles() {
  const cells = useGrid((s) => s.cells);
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const tempObject = useMemo(() => new THREE.Object3D(), []);

  // Hash on meaningful cell content so identical refetches don't re-randomize
  // particle positions. Without this, every grid refresh would shimmer all
  // 5,000+ particles to new random positions.
  const cellsHash = useMemo(
    () => cells.map((c) => `${c.row},${c.col},${c.pm25Mean.toFixed(1)}`).join('|'),
    [cells],
  );

  // Pre-compute particle positions and colors once per meaningful data change.
  const { positions, colors, count } = useMemo(() => {
    const pos: { x: number; y: number; z: number }[] = [];
    const cols: THREE.Color[] = [];

    for (const cell of cells) {
      const n = particleCountForPm25(cell.pm25Mean);
      const center = cellToWorld({ row: cell.row, col: cell.col });
      const color = threeColorForPm25(cell.pm25Mean);

      for (let p = 0; p < n; p++) {
        pos.push({
          x: center.x + (Math.random() - 0.5) * CELL_X * 0.85,
          y: 0.3 + Math.pow(Math.random(), 1.4) * 2.7,
          z: center.z + (Math.random() - 0.5) * CELL_Z * 0.85,
        });
        cols.push(color);
      }
    }

    return { positions: pos, colors: cols, count: pos.length };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cellsHash]);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh || count === 0) return;

    if (!mesh.instanceColor) {
      mesh.instanceColor = new THREE.InstancedBufferAttribute(
        new Float32Array(count * 3),
        3,
      );
    }

    for (let i = 0; i < count; i++) {
      const p = positions[i];
      tempObject.position.set(p.x, p.y, p.z);
      tempObject.scale.set(1, 1, 1);
      tempObject.rotation.set(0, 0, 0);
      tempObject.updateMatrix();
      mesh.setMatrixAt(i, tempObject.matrix);
      mesh.setColorAt(i, colors[i]);
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [positions, colors, count, tempObject]);

  if (count === 0) return null;

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, count]}
      raycast={() => null}
      castShadow={false}
      receiveShadow={false}
      frustumCulled={false}
    >
      <sphereGeometry args={[0.06, 6, 4]} />
      <meshBasicMaterial transparent opacity={0.85} depthWrite={false} />
    </instancedMesh>
  );
}
