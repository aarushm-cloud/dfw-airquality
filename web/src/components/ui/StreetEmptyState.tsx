import { useViewStore } from '../../state/view';
import { useSelectedCell } from '../../state/grid';
import { PANEL_WIDTH_PX } from './LeftPanel';

// DOM overlay for the "no cell selected" street state. Required to be DOM
// (not Drei <Text>) so the guidance text is screen-reader accessible —
// <Text> is 3D geometry, not real text. Centered horizontally over the
// canvas, offset right of the LeftPanel so it doesn't sit under chrome.
export function StreetEmptyState() {
  const view = useViewStore((s) => s.view);
  const cell = useSelectedCell();
  if (view !== 'street' || cell !== null) return null;

  return (
    <div
      role="status"
      className="fixed inset-0 z-10 flex items-center justify-center pointer-events-none"
      style={{ paddingLeft: PANEL_WIDTH_PX }}
    >
      <div className="bg-ink-900/85 backdrop-blur-sm border border-hairline rounded-sm px-5 py-3">
        <p className="font-mono uppercase text-[11px] tracking-wider text-stone-300">
          No air quality data &mdash; search a zip
        </p>
      </div>
    </div>
  );
}
