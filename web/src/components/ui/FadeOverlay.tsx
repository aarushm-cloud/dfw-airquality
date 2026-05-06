import { useEffect, useState } from 'react';
import { useViewStore } from '../../state/view';

// Simple cross-fade overlay (Option 2). setView fires synchronously at t=0
// so the camera snapshot in setView still runs before the scene swap; this
// overlay then fades a black div in over 150ms and out over 150ms to mask
// the brief blank-frame moment of the scene swap. Rapid toggle: each
// setView bumps transitionStartMs, the effect restarts with a new start,
// and the previous animation frame is cancelled. Latest action wins.
const FADE_DURATION_MS = 300;
const HALF = FADE_DURATION_MS / 2;

export function FadeOverlay() {
  const start = useViewStore((s) => s.transitionStartMs);
  const [opacity, setOpacity] = useState(0);

  useEffect(() => {
    if (start === 0) return;
    let raf = 0;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      const elapsed = Date.now() - start;
      if (elapsed < HALF) {
        setOpacity(elapsed / HALF);
      } else if (elapsed < FADE_DURATION_MS) {
        setOpacity(1 - (elapsed - HALF) / HALF);
      } else {
        setOpacity(0);
        return;
      }
      raf = requestAnimationFrame(tick);
    };

    tick();
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [start]);

  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none"
      style={{ backgroundColor: '#000', opacity, zIndex: 15 }}
    />
  );
}
