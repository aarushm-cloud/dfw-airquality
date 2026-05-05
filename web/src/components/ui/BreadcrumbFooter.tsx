import { useGrid, useSelectedCellMeta } from '../../state/grid';
import { BBOX } from '../../world/bbox';
// Vite supports JSON imports natively. tsconfig "moduleResolution: bundler"
// resolves them without needing resolveJsonModule.
import pkg from '../../../package.json';

const PKG_VERSION = (pkg as { version: string }).version;

const BUILD_META = `BBOX ${BBOX.west}/${BBOX.east}/${BBOX.south}/${BBOX.north} · IDW p=3 r=0.15° · v${PKG_VERSION}`;

export function BreadcrumbFooter() {
  const row = useGrid((s) => s.selectedCellRow);
  const col = useGrid((s) => s.selectedCellCol);
  const meta = useSelectedCellMeta();

  const hasCell = row !== null && col !== null;
  const resolvedZip = meta?.zip ?? null;
  const zipChunk = !hasCell
    ? null
    : meta?.metaStatus === 'loading'
      ? 'ZIP —'
      : resolvedZip
        ? `ZIP ${resolvedZip}`
        : 'ZIP —';

  // Resolved zip only — typed-zip disclosure stays in the info card.
  // The breadcrumb is ground-truth navigation state, not interaction artifact.
  const navPath = hasCell
    ? `AERIA.ATLAS > DFW > CITY OVERVIEW > CELL ${row}·${col} · ${zipChunk}`
    : 'AERIA.ATLAS > DFW > CITY OVERVIEW';

  return (
    <footer
      className={[
        'fixed bottom-0 left-0 right-0 z-10 pointer-events-none',
        'bg-ink-950/90',
        'border-t border-hairline',
        'px-4 py-2',
        'flex justify-between items-center gap-4',
      ].join(' ')}
    >
      <div className="font-mono uppercase text-[10px] tracking-wider text-stone-500 truncate">
        {navPath}
      </div>
      <div className="font-mono uppercase text-[9px] tracking-wider text-stone-600 whitespace-nowrap">
        {BUILD_META}
      </div>
    </footer>
  );
}
