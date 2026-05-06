import { create } from 'zustand';
import { useSceneStore } from './scene';

// Routing as its own domain. Future tabs ('time', 'route') extend this store
// without touching grid or scene state.
type View = 'city' | 'street';

type ViewState = {
  view: View;
  // Wall-clock timestamp of the most recent setView call, used by FadeOverlay
  // to drive a 300ms cross-fade. 0 means "no transition has happened yet" so
  // the initial mount doesn't fire a fade. Each setView bumps it; rapid
  // toggles restart the fade cycle (latest wins).
  transitionStartMs: number;
  setView: (next: View) => void;
};

export const useViewStore = create<ViewState>((set, get) => ({
  view: 'city',
  transitionStartMs: 0,
  setView: (next) => {
    // Capture city camera at the transition boundary, NOT on CityScene's
    // unmount cleanup. StrictMode double-invokes effect cleanups during dev,
    // and the first cleanup runs before <PerspectiveCamera makeDefault> has
    // installed itself — snapshotting there would cache the R3F default
    // camera (origin) and the next mount would restore that, producing a
    // "loads in zoomed in" bug. Tying snapshot to the user-driven view
    // transition instead means it only runs once, with the correct camera.
    const current = get().view;
    if (current === next) return;
    if (current === 'city' && next !== 'city') {
      useSceneStore.getState().snapshotCityCamera();
    }
    set({ view: next, transitionStartMs: Date.now() });
  },
}));
