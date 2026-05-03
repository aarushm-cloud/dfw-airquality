import { create } from 'zustand';
import { getHealth } from '../api/client';

export type Status = 'connecting' | 'warming' | 'ready' | 'disconnected';

type ConnectionState = {
  status: Status;
  uptimeSeconds: number;
  lastChecked: number | null;
  hasAttempted: boolean;
  poll: () => Promise<void>;
};

export const useConnection = create<ConnectionState>((set, get) => ({
  status: 'connecting',
  uptimeSeconds: 0,
  lastChecked: null,
  hasAttempted: false,

  poll: async () => {
    const checkedAt = Date.now();
    try {
      const health = await getHealth();
      set({
        status: health.cache_warm ? 'ready' : 'warming',
        uptimeSeconds: health.uptime_seconds,
        lastChecked: checkedAt,
        hasAttempted: true,
      });
    } catch {
      // First failure stays in 'connecting' so the UI doesn't flap on a slow
      // backend boot; any failure after that is a real disconnect.
      const isFirstAttempt = !get().hasAttempted;
      set({
        status: isFirstAttempt ? 'connecting' : 'disconnected',
        lastChecked: checkedAt,
        hasAttempted: true,
      });
    }
  },
}));
