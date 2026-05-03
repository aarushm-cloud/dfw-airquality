import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import {
  CELL_X,
  CELL_Z,
  GRID_SIZE,
  cellToLatLon,
  cellToWorld,
} from '../../world/bbox';
import { useGrid } from '../../state/grid';

const CELL_INSET = 0.96;
const CELL_SCALE_X = CELL_X * CELL_INSET;
const CELL_SCALE_Z = CELL_Z * CELL_INSET;
const TOTAL_CELLS = GRID_SIZE * GRID_SIZE;

const HOVER_Y = 0.02;
const SELECTED_Y = 0.03;

export function CellGrid() {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const hoverMeshRef = useRef<THREE.Mesh>(null);
  const selectedMeshRef = useRef<THREE.Mesh>(null);
  const hoveredInstanceRef = useRef<number | null>(null);

  const setSelectedCell = useGrid((s) => s.setSelectedCell);
  const selectedCell = useGrid((s) => s.selectedCell);

  const tempObject = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    for (let row = 0; row < GRID_SIZE; row++) {
      for (let col = 0; col < GRID_SIZE; col++) {
        const i = row * GRID_SIZE + col;
        const { x, z } = cellToWorld({ row, col });
        tempObject.position.set(x, 0.01, z);
        tempObject.rotation.set(-Math.PI / 2, 0, 0);
        tempObject.scale.set(CELL_SCALE_X, CELL_SCALE_Z, 1);
        tempObject.updateMatrix();
        mesh.setMatrixAt(i, tempObject.matrix);
      }
    }
    mesh.instanceMatrix.needsUpdate = true;
  }, [tempObject]);

  useEffect(() => {
    const sel = selectedMeshRef.current;
    if (!sel) return;
    if (selectedCell) {
      const { x, z } = cellToWorld(selectedCell);
      sel.position.set(x, SELECTED_Y, z);
      sel.visible = true;
    } else {
      sel.visible = false;
    }
  }, [selectedCell]);

  useEffect(() => {
    return () => {
      document.body.style.cursor = '';
    };
  }, []);

  const handlePointerMove = (e: ThreeEvent<PointerEvent>) => {
    const id = e.instanceId;
    if (id === undefined) return;
    if (id === hoveredInstanceRef.current) return;
    hoveredInstanceRef.current = id;
    const row = Math.floor(id / GRID_SIZE);
    const col = id % GRID_SIZE;
    const { x, z } = cellToWorld({ row, col });
    const hover = hoverMeshRef.current;
    if (hover) {
      hover.position.set(x, HOVER_Y, z);
      hover.visible = true;
    }
  };

  const handlePointerOver = (e: ThreeEvent<PointerEvent>) => {
    document.body.style.cursor = 'pointer';
    handlePointerMove(e);
  };

  const handlePointerOut = () => {
    hoveredInstanceRef.current = null;
    if (hoverMeshRef.current) hoverMeshRef.current.visible = false;
    document.body.style.cursor = '';
  };

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const id = e.instanceId;
    if (id === undefined) return;
    const row = Math.floor(id / GRID_SIZE);
    const col = id % GRID_SIZE;
    const { lat, lon } = cellToLatLon({ row, col });
    console.log(
      `[cell] (${row}, ${col}) | bbox: (${lat.toFixed(4)}, ${lon.toFixed(4)}) | zip: pending`,
    );
    setSelectedCell({ row, col });
  };

  return (
    <group>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, TOTAL_CELLS]}
        onPointerOver={handlePointerOver}
        onPointerMove={handlePointerMove}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial color="#1a1a26" transparent opacity={0.6} />
      </instancedMesh>

      <mesh
        ref={hoverMeshRef}
        rotation={[-Math.PI / 2, 0, 0]}
        scale={[CELL_SCALE_X, CELL_SCALE_Z, 1]}
        visible={false}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial color="#ffd166" transparent opacity={0.15} />
      </mesh>

      <mesh
        ref={selectedMeshRef}
        rotation={[-Math.PI / 2, 0, 0]}
        scale={[CELL_SCALE_X, CELL_SCALE_Z, 1]}
        visible={false}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial color="#ffd166" transparent opacity={0.3} />
      </mesh>
    </group>
  );
}
