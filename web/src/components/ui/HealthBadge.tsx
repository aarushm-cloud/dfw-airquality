import { useConnection, type Status } from '../../state/connection';

type StatusVariant = { label: string; dot: string };

const STATUS_VARIANTS: Record<Status, StatusVariant> = {
  connecting:   { label: 'CONNECTING',   dot: '#ffd166' },
  warming:      { label: 'WARMING UP',   dot: '#ffd166' },
  ready:        { label: 'READY',        dot: '#6fd0c5' },
  disconnected: { label: 'DISCONNECTED', dot: '#78716c' },
};

export function HealthBadge() {
  const status = useConnection((s) => s.status);
  const { label, dot } = STATUS_VARIANTS[status];
  const isPulsing = status === 'connecting';

  return (
    <div
      className={[
        'fixed bottom-10 left-3 z-10 pointer-events-auto',
        'flex items-center gap-2',
        'rounded-sm border border-hairline bg-ink-900/80 backdrop-blur-sm',
        'px-2 py-1',
        'font-mono text-[11px] uppercase tracking-wider text-stone-300',
      ].join(' ')}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${isPulsing ? 'animate-pulse' : ''}`}
        style={{ backgroundColor: dot }}
      />
      <span>{label}</span>
    </div>
  );
}
