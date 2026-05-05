import { create } from 'zustand';

// Routing as its own domain. Future tabs ('time', 'route') extend this store
// without touching grid or scene state.
type View = 'city' | 'street';

type ViewState = {
  view: View;
  setView: (next: View) => void;
};

export const useViewStore = create<ViewState>((set) => ({
  view: 'city',
  setView: (next) => set({ view: next }),
}));
