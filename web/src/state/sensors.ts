import { create } from 'zustand';
import { getSensors } from '../api/client';

type SensorsState = {
  status: 'idle' | 'loading' | 'ready' | 'error';
  count: number;
  fetchSensors: () => Promise<void>;
};

export const useSensorsStore = create<SensorsState>((set) => ({
  status: 'idle',
  count: 0,
  fetchSensors: async () => {
    set({ status: 'loading' });
    try {
      const data = await getSensors();
      set({ status: 'ready', count: data.count });
    } catch (err) {
      console.warn('[sensors] fetch failed:', err);
      set({ status: 'error' });
    }
  },
}));
