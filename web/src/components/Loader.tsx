import { useEffect, useRef, useState } from 'react';
import { useConnection, type Status as ConnectionStatus } from '../state/connection';

// Boot-time loader. Visible only when the connection store is in a loading
// state at first mount; an HMR save with an already-warm backend stays hidden.
// Split into LoaderContent (presentational) and Loader (state machine) so
// item 6 can reuse LoaderContent as a Suspense fallback for lazy-loaded
// CityScene without re-running the dismiss state machine.

const LOADING_STATES = new Set<ConnectionStatus>(['connecting', 'warming']);
const isLoading = (s: ConnectionStatus) => LOADING_STATES.has(s);

const MIN_VISIBLE_MS = 1000;
const FORCE_DISMISS_MS = 15_000;
const FADE_OUT_MS = 400;

type Phase = 'hidden' | 'loading' | 'dismissing' | 'dismissed';

const STATUS_LINES = ['Loading sensors', 'Building grid', 'Reading traffic'] as const;
const STATUS_DELAYS_MS = [0, 1400, 2800];

function LoaderContent({ dismissing = false }: { dismissing?: boolean }) {
  return (
    <div
      role="status"
      aria-label="Loading AERIA"
      className="fixed inset-0 z-20 flex items-center justify-center"
      style={{
        background:
          'radial-gradient(ellipse 80% 60% at 50% 70%, rgba(198, 109, 214, 0.04), transparent),' +
          'radial-gradient(ellipse 80% 60% at 50% 30%, rgba(255, 209, 102, 0.03), transparent),' +
          '#0a0a0f',
        opacity: dismissing ? 0 : 1,
        pointerEvents: dismissing ? 'none' : 'auto',
        transition: `opacity ${FADE_OUT_MS}ms ease-out`,
      }}
    >
      <div aria-hidden="true" className="flex flex-col items-center">
        <div
          className="font-display text-gold animate-aeria-reveal"
          style={{ fontSize: '80px', letterSpacing: '-0.02em', lineHeight: 1 }}
        >
          AERIA
        </div>

        {/* Status line: three strings stacked in a 1×1 grid cell so layout
            is stable. Each fades through a 4.2s cycle on staggered delays.
            Asymmetric base opacity is deliberate — under reduced motion the
            global rule collapses the animation to 0.01ms with `backwards`
            fill, so elements revert to their base styles. The first string's
            base opacity:1 keeps a static "Loading sensors" affordance; the
            other two stay at base opacity:0 to avoid stacking on top of it. */}
        <div className="mt-8 grid font-mono uppercase text-[10px] tracking-wider text-stone-400">
          {STATUS_LINES.map((line, i) => (
            <span
              key={line}
              className="row-start-1 col-start-1 animate-status-cycle"
              style={{
                opacity: i === 0 ? 1 : 0,
                animationDelay: `${STATUS_DELAYS_MS[i]}ms`,
              }}
            >
              {line}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Loader() {
  const status = useConnection((s) => s.status);
  const [phase, setPhase] = useState<Phase>(() =>
    isLoading(useConnection.getState().status) ? 'loading' : 'hidden',
  );
  const mountedAtRef = useRef(Date.now());

  // Arm the ready→dismiss transition once status leaves the loading set,
  // delayed so the loader is always visible for at least MIN_VISIBLE_MS.
  // Re-runs on status flips: a flap back into loading clears the timer.
  useEffect(() => {
    if (phase !== 'loading') return;
    if (isLoading(status)) return;
    const elapsed = Date.now() - mountedAtRef.current;
    const remaining = Math.max(0, MIN_VISIBLE_MS - elapsed);
    const id = setTimeout(() => setPhase('dismissing'), remaining);
    return () => clearTimeout(id);
  }, [phase, status]);

  // Safety valve: dismiss after FORCE_DISMISS_MS regardless of status.
  // Covers a hung /api/health (raw fetch has no timeout) — HealthBadge then
  // takes over surfacing connection state.
  useEffect(() => {
    if (phase !== 'loading') return;
    const elapsed = Date.now() - mountedAtRef.current;
    const remaining = Math.max(0, FORCE_DISMISS_MS - elapsed);
    const id = setTimeout(() => setPhase('dismissing'), remaining);
    return () => clearTimeout(id);
  }, [phase]);

  // Commit to dismiss: ignore status changes during the fade-out.
  useEffect(() => {
    if (phase !== 'dismissing') return;
    const id = setTimeout(() => setPhase('dismissed'), FADE_OUT_MS);
    return () => clearTimeout(id);
  }, [phase]);

  if (phase === 'hidden' || phase === 'dismissed') return null;
  return <LoaderContent dismissing={phase === 'dismissing'} />;
}
