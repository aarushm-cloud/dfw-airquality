import { useViewStore } from '../../state/view';

type Tab = {
  key: 'city' | 'street' | 'time' | 'route';
  label: string;
  enabled: boolean;
  tooltip: string | null;
};

const TABS: readonly Tab[] = [
  { key: 'city',   label: 'City overview', enabled: true,  tooltip: null },
  { key: 'street', label: 'Street view',   enabled: true,  tooltip: null },
  { key: 'time',   label: 'Time machine',  enabled: false, tooltip: 'Historical playback — coming soon' },
  { key: 'route',  label: 'Route lab',     enabled: false, tooltip: 'Cleanest path optimizer — coming soon' },
] as const;

function TabButton({ tab, active, onClick }: { tab: Tab; active: boolean; onClick: () => void }) {
  if (tab.enabled) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={[
          'relative px-3 py-1.5',
          active ? 'bg-ink-800 border-b-2 border-gold' : 'border-b-2 border-transparent',
          'font-sans text-[11px]',
          active ? 'text-stone-200' : 'text-stone-400 hover:text-stone-200',
          'rounded-sm',
          'cursor-pointer',
          'focus:outline-none',
          'transition-colors',
        ].join(' ')}
      >
        {tab.label}
      </button>
    );
  }

  return (
    <button
      type="button"
      aria-disabled="true"
      onClick={(e) => e.preventDefault()}
      // group enables sibling tooltip on both hover and keyboard focus.
      // Use aria-disabled (not native disabled) so focus/hover events still
      // fire — native disabled silently swallows pointer events on most browsers.
      className={[
        'group relative px-3 py-1.5',
        'font-sans text-[11px] text-stone-500',
        'cursor-not-allowed',
        'rounded-sm',
        'focus:outline-none',
      ].join(' ')}
    >
      {tab.label}
      <span
        role="tooltip"
        className={[
          'absolute top-full left-1/2 -translate-x-1/2 mt-1',
          'whitespace-nowrap',
          'bg-ink-800 border border-hairline rounded-sm',
          'px-2 py-1',
          'font-mono uppercase text-[9px] tracking-wider text-stone-400',
          'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
          'transition-opacity pointer-events-none',
        ].join(' ')}
      >
        {tab.tooltip}
      </span>
    </button>
  );
}

export function TopNav() {
  const view = useViewStore((s) => s.view);
  const setView = useViewStore((s) => s.setView);

  return (
    <nav
      aria-label="View"
      className={[
        'fixed top-4 left-1/2 -translate-x-1/2 z-20 pointer-events-auto',
        'bg-ink-900/85 backdrop-blur-sm',
        'border border-hairline rounded-sm',
        'p-1 flex gap-1',
      ].join(' ')}
    >
      {TABS.map((tab) => (
        <TabButton
          key={tab.key}
          tab={tab}
          active={tab.key === view}
          onClick={() => {
            if (tab.key === 'city' || tab.key === 'street') setView(tab.key);
          }}
        />
      ))}
    </nav>
  );
}
