import { create } from 'zustand';
import {
  postRoute,
  RouteApiError,
  type GeocodeSuggestion,
  type RouteResponse,
} from '../api/client';

// Route Lab UI state. Typeahead suggestions live inside <AddressInput> since
// they're per-input transient state — only the canonical selected text needs
// to round-trip through the store. result + status drive both the stats card
// and the in-scene polylines.

type Status = 'idle' | 'submitting' | 'success' | 'error';

type RouteState = {
  startInput: string;
  endInput: string;
  status: Status;
  result: RouteResponse | null;
  // User-facing message — already mapped from the underlying RouteApiError.
  // Empty string = no error to display.
  errorMessage: string;
  // Sticky for the session once the backend signals demo mode. Drives the
  // "preview only" banner + disables the submit button so the user can't
  // re-fire a known-failing request.
  routingDisabled: boolean;

  setStartInput: (s: string) => void;
  setEndInput: (s: string) => void;
  pickStart: (s: GeocodeSuggestion) => void;
  pickEnd: (s: GeocodeSuggestion) => void;
  submit: () => Promise<void>;
  clearError: () => void;
};

// True when the backend's 503 detail carries the routing-disabled sentinel
// shape ({code: "routing_disabled", message: "..."}). FastAPI passes
// HTTPException(detail=...) through as-is, so the dict reaches the client
// intact (provided client.ts doesn't coerce it to string).
function isRoutingDisabled(err: unknown): boolean {
  if (!(err instanceof RouteApiError)) return false;
  if (err.status !== 503) return false;
  const d = err.detail;
  return (
    typeof d === 'object' &&
    d !== null &&
    (d as { code?: unknown }).code === 'routing_disabled'
  );
}

// Backend → user-facing string mapping. Centralized so both the store and
// any future caller (e.g. a retry hook) produce identical copy.
function userMessageFor(err: unknown): string {
  if (err instanceof RouteApiError) {
    // Detail may be a plain string (every other error path) or a structured
    // dict (the routing-disabled case, handled separately upstream). Narrow
    // before the substring checks so an object detail doesn't crash.
    const detail = typeof err.detail === 'string' ? err.detail.toLowerCase() : '';
    if (err.status === 400) {
      return "Couldn't find that address. Try a more specific name or full street address.";
    }
    if (err.status === 404) {
      if (detail.includes('outside')) {
        return 'Address is outside the DFW metro. Try a Dallas/Fort Worth address.';
      }
      if (detail.includes('walking path')) {
        return 'No walking path exists between these two points.';
      }
      // Fall through to the generic 404 message — matches the
      // 'service unavailable' bucket so users see something coherent.
      return 'Route service unavailable. Try again in a moment.';
    }
    if (err.status === 422) {
      return 'Please enter both start and end addresses.';
    }
    if (err.status === 502 || err.status === 503) {
      return 'Route service unavailable. Try again in a moment.';
    }
  }
  return 'Route service unavailable. Try again in a moment.';
}

export const useRouteStore = create<RouteState>((set, get) => ({
  startInput: '',
  endInput: '',
  status: 'idle',
  result: null,
  errorMessage: '',
  routingDisabled: false,

  setStartInput: (s) => set({ startInput: s }),
  setEndInput: (s) => set({ endInput: s }),
  pickStart: (s) => set({ startInput: s.display_name }),
  pickEnd: (s) => set({ endInput: s.display_name }),
  clearError: () => set({ status: 'idle', errorMessage: '' }),

  submit: async () => {
    const { startInput, endInput, routingDisabled } = get();
    if (routingDisabled) return;

    const start = startInput.trim();
    const end = endInput.trim();

    if (!start || !end) {
      set({
        status: 'error',
        errorMessage: 'Please enter both start and end addresses.',
      });
      return;
    }

    set({ status: 'submitting', errorMessage: '' });
    try {
      const result = await postRoute({ start, end });
      set({ status: 'success', result, errorMessage: '' });
    } catch (err) {
      if (isRoutingDisabled(err)) {
        // Sticky banner takes the place of the error toast — no message.
        set({
          status: 'idle',
          errorMessage: '',
          result: null,
          routingDisabled: true,
        });
        return;
      }
      set({
        status: 'error',
        errorMessage: userMessageFor(err),
        // Drop any stale result so the polylines clear on a failed retry.
        result: null,
      });
    }
  },
}));
