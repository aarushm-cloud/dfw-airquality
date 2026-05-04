import { create } from 'zustand';
import {
  getGrid,
  getCellAt,
  getCellByZip,
  ZipNotCoveredError,
  type GridResponse,
} from '../api/client';
import {
  cellToLatLon,
  cellToWorld,
  latLonToCell,
  GRID_SIZE,
  SOURCE_GRID_SIZE,
} from '../world/bbox';
import { useSceneStore } from './scene';
import { panCameraTo } from '../components/scene/cameraPan';

export type GridStatus = 'idle' | 'loading' | 'ready' | 'error';

export type GridData = {
  lats: number[];
  lons: number[];
  pm25: number[][];
  confidence: number[][];
  generatedAt: string;
};

export type CellSummary = {
  row: number;
  col: number;
  centerLat: number;
  centerLon: number;
  pm25Mean: number;
  pm25Max: number;
  confidenceMin: number;
};

export type SelectedCellMeta = {
  zip: string | null;
  neighborhood: string | null;
  metaStatus: 'loading' | 'ready' | 'error';
};

type GridState = {
  status: GridStatus;
  raw: GridData | null;
  cells: CellSummary[];

  selectedCellRow: number | null;
  selectedCellCol: number | null;
  selectedCellMeta: SelectedCellMeta | null;

  fetchGrid: () => Promise<void>;
  // pan defaults to false — most selection paths (click, future pin) shouldn't
  // move the camera. Explicit-search paths opt in by passing { pan: true }.
  selectCellByCoord: (row: number, col: number, opts?: { pan?: boolean }) => Promise<void>;
  selectCellByZip: (zip: string) => Promise<void>;
  clearSelection: () => void;
};

function validatePayload(data: GridResponse): void {
  const N = SOURCE_GRID_SIZE;
  if (!Array.isArray(data.lats) || data.lats.length !== N) {
    throw new Error(`Bad grid payload: expected lats[${N}], got ${data.lats?.length}`);
  }
  if (!Array.isArray(data.lons) || data.lons.length !== N) {
    throw new Error(`Bad grid payload: expected lons[${N}], got ${data.lons?.length}`);
  }
  if (!Array.isArray(data.pm25) || data.pm25.length !== N) {
    throw new Error(`Bad grid payload: expected pm25[${N}][...], got ${data.pm25?.length}`);
  }
  if (!Array.isArray(data.pm25[0]) || data.pm25[0].length !== N) {
    throw new Error(`Bad grid payload: expected pm25[*][${N}], got ${data.pm25?.[0]?.length}`);
  }
  if (!Array.isArray(data.confidence) || data.confidence.length !== N) {
    throw new Error(`Bad grid payload: expected confidence[${N}][...]`);
  }
  if (!Array.isArray(data.confidence[0]) || data.confidence[0].length !== N) {
    throw new Error(`Bad grid payload: expected confidence[*][${N}]`);
  }
}

function aggregateCells(data: GridResponse): CellSummary[] {
  const cells: CellSummary[] = [];
  const SRC = SOURCE_GRID_SIZE;
  const DST = GRID_SIZE;

  for (let row = 0; row < DST; row++) {
    for (let col = 0; col < DST; col++) {
      const iStart = Math.floor((row * SRC) / DST);
      const iEnd = Math.floor(((row + 1) * SRC) / DST);
      const jStart = Math.floor((col * SRC) / DST);
      const jEnd = Math.floor(((col + 1) * SRC) / DST);

      let sum = 0;
      let max = -Infinity;
      let confMin = Infinity;
      let count = 0;
      for (let i = iStart; i < iEnd; i++) {
        for (let j = jStart; j < jEnd; j++) {
          const v = data.pm25[i][j];
          const c = data.confidence[i][j];
          sum += v;
          if (v > max) max = v;
          if (c < confMin) confMin = c;
          count++;
        }
      }

      const { lat, lon } = cellToLatLon({ row, col });
      cells.push({
        row,
        col,
        centerLat: lat,
        centerLon: lon,
        pm25Mean: sum / count,
        pm25Max: max,
        confidenceMin: confMin,
      });
    }
  }
  return cells;
}

// Monotonic token. Each new selection bumps it; in-flight resolutions check
// before writing back, so a stale zip lookup can't clobber a newer selection.
let _selectionToken = 0;

export const useGrid = create<GridState>((set, get) => ({
  status: 'idle',
  raw: null,
  cells: [],
  selectedCellRow: null,
  selectedCellCol: null,
  selectedCellMeta: null,

  fetchGrid: async () => {
    set({ status: 'loading' });
    try {
      const data = await getGrid();
      validatePayload(data);
      const cells = aggregateCells(data);
      set({
        status: 'ready',
        raw: {
          lats: data.lats,
          lons: data.lons,
          pm25: data.pm25,
          confidence: data.confidence,
          generatedAt: data.timestamp ?? data.generated_at ?? '',
        },
        cells,
      });
    } catch (err) {
      console.error('[grid] fetch failed:', err);
      set({ status: 'error' });
    }
  },

  selectCellByCoord: async (row, col, opts) => {
    const token = ++_selectionToken;
    const pan = opts?.pan ?? false;

    set({
      selectedCellRow: row,
      selectedCellCol: col,
      selectedCellMeta: { zip: null, neighborhood: null, metaStatus: 'loading' },
    });

    const cell = get().cells.find((c) => c.row === row && c.col === col);
    if (pan) {
      const { controls, camera } = useSceneStore.getState();
      if (controls && camera && cell) {
        const world = cellToWorld({ row, col });
        panCameraTo(controls, camera, world);
      }
    }

    if (!cell) {
      if (token === _selectionToken) {
        set({ selectedCellMeta: { zip: null, neighborhood: null, metaStatus: 'error' } });
      }
      return;
    }

    try {
      const result = await getCellAt(cell.centerLat, cell.centerLon);
      if (token !== _selectionToken) return;
      set({
        selectedCellMeta: {
          zip: result.zip,
          neighborhood: result.neighborhood,
          metaStatus: 'ready',
        },
      });
    } catch (err) {
      if (token !== _selectionToken) return;
      set({ selectedCellMeta: { zip: null, neighborhood: null, metaStatus: 'error' } });
      console.warn('[selection] zip lookup failed:', err);
    }
  },

  selectCellByZip: async (zip) => {
    const result = await getCellByZip(zip);
    const cellCoord = latLonToCell({ lat: result.lat, lon: result.lon });
    if (!cellCoord) throw new ZipNotCoveredError(zip);
    await get().selectCellByCoord(cellCoord.row, cellCoord.col, { pan: true });
  },

  clearSelection: () => {
    ++_selectionToken;
    set({
      selectedCellRow: null,
      selectedCellCol: null,
      selectedCellMeta: null,
    });
  },
}));
