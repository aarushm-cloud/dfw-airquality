import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useGrid, useMetroAggregates } from '../../../state/grid';
import { useSensorsStore } from '../../../state/sensors';
import { AQI_COLOR } from '../../../world/aqi';

const RELATIVE_TIME_TICK_MS = 30_000;

function formatRelative(generatedAt: string, now: number): string {
  if (!generatedAt) return '—';
  const t = Date.parse(generatedAt);
  if (Number.isNaN(t)) return '—';
  const ageSec = Math.max(0, Math.floor((now - t) / 1000));
  if (ageSec < 60) return 'JUST NOW';
  const ageMin = Math.floor(ageSec / 60);
  if (ageMin === 1) return '1 MIN AGO';
  if (ageMin < 60) return `${ageMin} MIN AGO`;
  const ageHr = Math.floor(ageMin / 60);
  if (ageHr === 1) return '1 HR AGO';
  return `${ageHr} HR AGO`;
}

function Separator() {
  return <span className="text-stone-700">·</span>;
}

export function TopStatusBar() {
  const sensorCount = useSensorsStore((s) => s.count);
  const sensorStatus = useSensorsStore((s) => s.status);
  const metro = useMetroAggregates();
  const generatedAt = useGrid((s) => s.raw?.generatedAt ?? '');

  // Drives the relative-time refresh. setInterval cleanup makes this
  // idempotent under StrictMode's double-mount.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), RELATIVE_TIME_TICK_MS);
    return () => clearInterval(id);
  }, []);

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: '16px',
        right: '16px',
        zIndex: 2147483000,
        transform: 'translateZ(0)',
        pointerEvents: 'auto',
      }}
      className={[
        'isolate',
        'bg-ink-900/85 backdrop-blur-sm',
        'border border-hairline rounded-sm',
        'px-4 py-3',
        'flex items-center gap-3',
        'font-mono uppercase text-[10px] tracking-wider',
      ].join(' ')}
    >
      {/* Live indicator */}
      <span className="flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-block h-1.5 w-1.5 rounded-full bg-gold animate-pulse"
        />
        <span className="text-stone-300">LIVE</span>
      </span>

      <Separator />

      {/* Sensor count */}
      <span className="text-stone-400">
        {sensorStatus === 'ready' ? `${sensorCount} SENSORS` : '— SENSORS'}
      </span>

      <Separator />

      {/* Metro PM2.5 */}
      <span className="flex items-center gap-1.5">
        {metro && (
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: AQI_COLOR[metro.category] }}
          />
        )}
        <span className="font-sans normal-case text-[12px] text-stone-200">
          {metro ? metro.pm25Mean.toFixed(1) : '—'}
        </span>
        <span className="text-[9px] text-stone-500">µg/m³</span>
      </span>

      {/* Wind metric intentionally omitted — /api/sensors does not expose wind.
          See web/CONTRACT.md future-cleanup. */}

      <Separator />

      {/* Last updated */}
      <span className="text-stone-500">
        UPDATED {formatRelative(generatedAt, now)}
      </span>
    </div>,
    document.body,
  );
}
