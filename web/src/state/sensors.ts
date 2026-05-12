import { create } from 'zustand';
import { getSensors, type FilteredSensor } from '../api/client';

type SensorsState = {
  status: 'idle' | 'loading' | 'ready' | 'error';
  count: number;
  filtered: FilteredSensor[];
  fetchSensors: () => Promise<void>;
};

export const useSensorsStore = create<SensorsState>((set) => ({
  status: 'idle',
  count: 0,
  filtered: [],
  fetchSensors: async () => {
    set({ status: 'loading' });
    try {
      const data = await getSensors();
      set({
        status: 'ready',
        count: data.count,
        filtered: data.filtered_sensors,
      });
    } catch (err) {
      console.warn('[sensors] fetch failed:', err);
      // Do not clear `filtered` on error — stale data is preferable to wrongly
      // hiding a known fault while the backend is unreachable.
      set({ status: 'error' });
    }
  },
}));
