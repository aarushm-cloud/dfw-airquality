import { createPortal } from 'react-dom';
import { useViewStore } from '../../../state/view';
import { useRouteStore } from '../../../state/route';

// Top-right card matching CellInfoCard's visual chrome — same portal pattern,
// same hairline border, same JetBrains Mono numerics. Renders when view ===
// 'route' AND a route has been computed (or is computing). Hidden in city /
// street views even if a result exists, so the user's cell-info workflow
// isn't covered up.

const SHARED_CHROME =
  'isolate bg-ink-900/95 backdrop-blur-sm border border-hairline rounded-sm p-3';

const SHARED_FRAME = {
  position: 'fixed' as const,
  top: '180px',
  right: '24px',
  zIndex: 2147483000,
  transform: 'translateZ(0)',
  width: '220px',
  pointerEvents: 'auto' as const,
};

function formatComputedAt(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return timestamp;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function RouteStatsCard() {
  const view = useViewStore((s) => s.view);
  const status = useRouteStore((s) => s.status);
  const result = useRouteStore((s) => s.result);

  if (view !== 'route') return null;

  // Loading state — subtle pulse on a stats placeholder, not a full-screen
  // spinner. Stays in the card slot so the user knows where the answer
  // will appear.
  if (status === 'submitting' && !result) {
    return createPortal(
      <div style={SHARED_FRAME} className={SHARED_CHROME}>
        <div className="font-mono uppercase text-[10px] tracking-wider text-gold animate-pulse">
          Cleanest route
        </div>
        <div className="mt-3 space-y-2">
          <div className="h-6 w-2/3 bg-ink-800 rounded-sm animate-pulse" />
          <div className="h-3 w-1/2 bg-ink-800 rounded-sm animate-pulse" />
          <div className="h-3 w-3/4 bg-ink-800 rounded-sm animate-pulse" />
        </div>
      </div>,
      document.body,
    );
  }

  if (!result) return null;

  const distanceKm = result.cleanest.distance_m / 1000;

  const timeDeltaMin = (result.cleanest.walk_seconds - result.shortest.walk_seconds) / 60;
  // Brief: suppress when the cleanest route is the same length or shorter
  // than the shortest. Round half-up; a 0.4-min delta still suppresses.
  const showTimeDelta = timeDeltaMin > 0.5;

  const showExposureDelta = result.shortest.total_exposure > 0;
  const exposurePct = showExposureDelta
    ? ((result.shortest.total_exposure - result.cleanest.total_exposure) /
        result.shortest.total_exposure) *
      100
    : 0;

  return createPortal(
    <div style={SHARED_FRAME} className={SHARED_CHROME}>
      <div className="font-mono uppercase text-[10px] tracking-wider text-gold">
        Cleanest route
      </div>

      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="font-display text-[28px] leading-none text-stone-100">
          {distanceKm.toFixed(1)}
        </span>
        <span className="font-mono uppercase text-[10px] tracking-wider text-stone-500">
          km
        </span>
      </div>

      <div className="mt-2 flex flex-col gap-1 font-mono text-[11px] text-stone-300">
        {showTimeDelta && (
          <div>
            <span className="text-stone-500">+</span>
            {Math.round(timeDeltaMin)}
            <span className="text-stone-500"> min vs shortest</span>
          </div>
        )}
        {showExposureDelta && (
          <div>
            {Math.round(exposurePct)}
            <span className="text-stone-500">% less exposure</span>
          </div>
        )}
      </div>

      <div className="mt-3 pt-2 border-t border-hairline font-mono text-[9px] tracking-wider text-stone-500">
        Computed {formatComputedAt(result.timestamp)}
      </div>
    </div>,
    document.body,
  );
}
