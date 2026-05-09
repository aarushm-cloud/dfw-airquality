import { type FormEvent } from 'react';
import { useViewStore } from '../../../state/view';
import { useRouteStore } from '../../../state/route';
import { AddressInput } from './AddressInput';
import { PANEL_WIDTH_PX } from './LeftPanel';

// Replaces LeftPanel when view === 'route'. Same width + chrome so the
// 3D scene below stays at the identical horizontal offset.

export function RouteLabPanel() {
  const view = useViewStore((s) => s.view);
  const startInput = useRouteStore((s) => s.startInput);
  const endInput = useRouteStore((s) => s.endInput);
  const setStartInput = useRouteStore((s) => s.setStartInput);
  const setEndInput = useRouteStore((s) => s.setEndInput);
  const pickStart = useRouteStore((s) => s.pickStart);
  const pickEnd = useRouteStore((s) => s.pickEnd);
  const status = useRouteStore((s) => s.status);
  const errorMessage = useRouteStore((s) => s.errorMessage);
  const submit = useRouteStore((s) => s.submit);

  if (view !== 'route') return null;

  const submitting = status === 'submitting';

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit();
  }

  return (
    <aside
      style={{ width: `${PANEL_WIDTH_PX}px` }}
      className={[
        'scrollable-panel',
        'fixed top-0 left-0 bottom-0 z-10',
        'pointer-events-auto',
        'bg-ink-900/85 backdrop-blur-sm',
        'border-r border-hairline',
        'p-5 overflow-y-auto',
      ].join(' ')}
    >
      <div className="border-b border-hairline pb-4 mb-4">
        <div className="font-display text-[22px] leading-none text-stone-100">AERIA</div>
        <div className="font-mono uppercase text-[10px] tracking-wider text-stone-500 mt-1">
          Route lab
        </div>
      </div>

      <div className="font-mono uppercase text-[10px] tracking-wider text-stone-400 mb-3">
        Cleanest path optimizer
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <AddressInput
          inputId="route-start"
          label="Start"
          value={startInput}
          onChange={setStartInput}
          onPick={pickStart}
          placeholder="e.g. Mockingbird Station Dallas"
          disabled={submitting}
        />
        <AddressInput
          inputId="route-end"
          label="End"
          value={endInput}
          onChange={setEndInput}
          onPick={pickEnd}
          placeholder="e.g. Klyde Warren Park Dallas"
          disabled={submitting}
        />
        <button
          type="submit"
          disabled={submitting}
          className={[
            'mt-1 px-3 py-2',
            'border border-gold/60 rounded-sm',
            'text-gold font-mono uppercase text-[10px] tracking-wider',
            'cursor-pointer',
            'hover:bg-gold/10 hover:border-gold',
            'focus:outline-none focus:border-gold',
            'transition-colors',
            'disabled:cursor-wait disabled:opacity-60',
          ].join(' ')}
        >
          {submitting ? 'Finding route…' : 'Find route'}
        </button>
      </form>

      {errorMessage && (
        <div
          role="alert"
          className={[
            'mt-4 p-2',
            'border border-magenta/60 rounded-sm',
            'font-sans text-[11px] leading-snug text-stone-300',
          ].join(' ')}
        >
          {errorMessage}
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-hairline">
        <div className="font-mono uppercase text-[9px] tracking-wider text-stone-500 leading-relaxed">
          Cleanest detours through lower PM₂.₅ cells; shortest minimizes walking
          distance only. Both walks are computed at 1.4&nbsp;m/s.
        </div>
      </div>
    </aside>
  );
}
