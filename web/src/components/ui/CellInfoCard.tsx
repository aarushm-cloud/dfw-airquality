import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
// Mount animation removed: the rAF-driven opacity/translate flip was leaving
// the card invisible. Add it back later only if it can be done without
// gating initial visibility on a state flip.
import { useGrid, useSelectedCell, useSelectedCellMeta, useSearchedZip } from '../../state/grid';
import { AQI_COLOR, AQI_LABEL, classifyPm25, LOW_CONFIDENCE_THRESHOLD } from '../../world/aqi';

const ZIP_LOADING_GRACE_MS = 1500;

function ZipLine({
  metaStatus,
  zip,
  loadStartedAt,
  searchedZip,
}: {
  metaStatus: 'loading' | 'ready' | 'error';
  zip: string | null;
  loadStartedAt: number;
  searchedZip: string | null;
}) {
  // Drives the "—" → "unavailable" fallback at 1500ms when a load drags.
  const [staleAt, setStaleAt] = useState(false);
  useEffect(() => {
    setStaleAt(false);
    const elapsed = performance.now() - loadStartedAt;
    if (elapsed >= ZIP_LOADING_GRACE_MS) {
      setStaleAt(true);
      return;
    }
    const t = window.setTimeout(
      () => setStaleAt(true),
      ZIP_LOADING_GRACE_MS - elapsed,
    );
    return () => window.clearTimeout(t);
  }, [loadStartedAt]);

  let body: ReactNode;
  if (metaStatus === 'loading') {
    body = staleAt
      ? <>ZIP <span className="text-stone-500">unavailable</span></>
      : <>ZIP <span className="text-stone-500">—</span></>;
  } else if (metaStatus === 'ready') {
    if (!zip) {
      body = <>ZIP <span className="text-stone-500">unavailable</span></>;
    } else if (searchedZip && searchedZip !== zip) {
      // Disclosure fires only on zip mismatch (a soft-edge zip mapping to a
      // neighbor). Cell mismatch is intentionally NOT disclosed — see CONTRACT.
      body = (
        <>
          ZIP <span className="text-stone-300">{zip}</span>
          <span className="text-stone-500"> (you typed {searchedZip})</span>
        </>
      );
    } else {
      body = <>ZIP <span className="text-stone-300">{zip}</span></>;
    }
  } else {
    body = <>ZIP <span className="text-stone-500">unavailable</span></>;
  }
  return <div className="font-mono uppercase text-[12px] text-stone-300">{body}</div>;
}

function PlaceholderButton({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <button
      type="button"
      aria-disabled="true"
      onClick={(e) => e.preventDefault()}
      className={[
        'flex-1 px-3 py-2',
        'border border-hairline rounded-sm',
        'text-stone-500 font-mono uppercase text-[10px] tracking-wider',
        'cursor-not-allowed',
        'hover:border-stone-700',
        'focus:outline-none focus:border-stone-700',
        'transition-colors',
        'relative group',
      ].join(' ')}
    >
      {label}
      <span
        className={[
          'absolute -top-8 left-1/2 -translate-x-1/2',
          'bg-ink-800 border border-hairline rounded-sm',
          'px-2 py-1 text-[10px] text-stone-400',
          'opacity-0 group-hover:opacity-100 group-focus:opacity-100',
          'transition-opacity pointer-events-none whitespace-nowrap',
        ].join(' ')}
      >
        {tooltip}
      </span>
    </button>
  );
}

export function CellInfoCard() {
  const selectedCellRow = useGrid((s) => s.selectedCellRow);
  const selectedCellCol = useGrid((s) => s.selectedCellCol);
  const selectedCellMeta = useSelectedCellMeta();
  const cell = useSelectedCell();
  const searchedZip = useSearchedZip();
  const clearSelection = useGrid((s) => s.clearSelection);

  // Reset the zip-loading timer whenever the selection changes.
  const loadStartedAt = useMemo(() => performance.now(), [selectedCellRow, selectedCellCol]);

  if (selectedCellRow === null || selectedCellCol === null) return null;

  const pm25 = cell?.pm25Mean ?? 0;
  const category = classifyPm25(pm25);
  const lat = cell?.centerLat ?? 0;
  const lon = cell?.centerLon ?? 0;
  const conf = cell?.confidenceMin ?? 1;
  const meta = selectedCellMeta ?? {
    zip: null,
    neighborhood: null,
    metaStatus: 'loading' as const,
  };

  // Rendered via portal directly into <body> to escape the React tree's
  // stacking context entirely. translateZ(0) forces a separate compositor
  // layer so the WebGL canvas can't visually obscure the card.
  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: '180px',
        right: '340px',
        zIndex: 2147483000,
        transform: 'translateZ(0)',
        width: '180px',
        pointerEvents: 'auto',
      }}
      className={[
        'isolate',
        'bg-ink-900/95 backdrop-blur-sm',
        'border border-hairline rounded-sm',
        'p-3',
      ].join(' ')}
    >
      <div className="flex items-start justify-between">
        <div>
          <ZipLine
            metaStatus={meta.metaStatus}
            zip={meta.zip}
            loadStartedAt={loadStartedAt}
            searchedZip={searchedZip}
          />
          <div className="font-mono uppercase text-[11px] tracking-wider text-stone-500 mt-0.5">
            Cell {selectedCellRow}·{selectedCellCol}
          </div>
        </div>
        <button
          type="button"
          onClick={clearSelection}
          aria-label="Close"
          className="text-stone-500 hover:text-stone-300 text-[16px] leading-none px-1 -mt-1 -mr-1"
        >
          ×
        </button>
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="font-display text-[30px] leading-none text-stone-100">
          {pm25.toFixed(1)}
        </span>
        <span className="font-mono uppercase text-[10px] tracking-wider text-stone-500">
          µg/m³
        </span>
      </div>

      {conf < LOW_CONFIDENCE_THRESHOLD && (
        <div className="font-mono text-[9px] uppercase text-stone-500 mt-1">
          · LOW CONFIDENCE · MAY BE UNRELIABLE
        </div>
      )}

      <div className="mt-1.5 flex items-center gap-2">
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: AQI_COLOR[category] }}
        />
        <span className="font-mono uppercase text-[10px] tracking-wider text-stone-300">
          {AQI_LABEL[category]}
        </span>
      </div>

      <div className="mt-3 pt-2 border-t border-hairline font-mono text-[9px] tracking-wider text-stone-500">
        LAT {lat.toFixed(4)} · LON {lon.toFixed(4)}
      </div>

      <div className="mt-3 flex flex-col gap-2">
        <PlaceholderButton label="Drop into street" tooltip="Available in Session 6" />
        <PlaceholderButton label="Pin" tooltip="Coming soon" />
      </div>
    </div>,
    document.body,
  );
}
