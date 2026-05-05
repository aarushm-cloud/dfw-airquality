import { useGrid, useSelectedCell, useSelectedCellMeta, useMetroAggregates } from '../../state/grid';
import {
  AQI_COLOR,
  AQI_LABEL,
  classifyPm25,
  confidenceLabel,
  LOW_CONFIDENCE_THRESHOLD,
} from '../../world/aqi';
import {
  HEALTH_GUIDANCE,
  GUIDANCE_SOURCE_URL,
  GUIDANCE_SOURCE_LABEL,
} from '../../world/healthGuidance';

// Locked at 280px — ZipSearch left offset (left-[296px]) and any future top
// chrome math depend on this. Update CONTRACT if changed.
export const PANEL_WIDTH_PX = 280;

function GuidanceList({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2">
          <span
            aria-hidden="true"
            className="mt-0.5 inline-block h-4 w-4 flex-shrink-0 rounded-sm border border-hairline"
          />
          <span className="font-sans text-[12px] leading-snug text-stone-300">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function SectionHeader({ children }: { children: string }) {
  return (
    <div className="font-mono uppercase text-[10px] tracking-wider text-stone-400 mb-2">
      {children}
    </div>
  );
}

export function LeftPanel() {
  const cell = useSelectedCell();
  const meta = useSelectedCellMeta();
  const metro = useMetroAggregates();
  const status = useGrid((s) => s.status);

  const hasCell = cell !== null;
  const category = hasCell ? classifyPm25(cell.pm25Mean) : metro?.category ?? null;
  const guidance = category ? HEALTH_GUIDANCE[category] : null;

  const resolvedZip = meta?.zip ?? null;
  const metaStatus = meta?.metaStatus;

  let zipLabel: string;
  if (!hasCell) {
    zipLabel = 'METRO AVERAGE';
  } else if (metaStatus === 'loading') {
    zipLabel = `CELL ${cell.row}·${cell.col} · ZIP —`;
  } else if (resolvedZip) {
    zipLabel = `CELL ${cell.row}·${cell.col} · ZIP ${resolvedZip}`;
  } else {
    zipLabel = `CELL ${cell.row}·${cell.col} · ZIP UNAVAILABLE`;
  }

  const pm25 = hasCell ? cell.pm25Mean : metro?.pm25Mean ?? 0;
  const conf = hasCell ? cell.confidenceMin : metro?.confidenceMean ?? 0;
  const isLowConf = hasCell && cell.confidenceMin < LOW_CONFIDENCE_THRESHOLD;

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
      {/* Section 1 — Header */}
      <div className="border-b border-hairline pb-4 mb-4">
        <div className="font-display text-[22px] leading-none text-stone-100">AERIA</div>
        <div className="font-mono uppercase text-[10px] tracking-wider text-stone-500 mt-1">
          DFW · PM₂.₅ Atlas
        </div>
      </div>

      {/* Section 2 — Status header */}
      <div className="mb-5">
        <div className="font-mono uppercase text-[10px] tracking-wider text-stone-500">
          {zipLabel}
        </div>

        {category && (
          <div className="mt-1.5 flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: AQI_COLOR[category] }}
            />
            <span className="font-mono uppercase text-[11px] tracking-wider text-stone-300">
              {AQI_LABEL[category]}
            </span>
          </div>
        )}

        <div className="mt-2 flex items-baseline gap-1.5">
          <span className="font-display text-[32px] leading-none text-stone-100">
            {status === 'ready' ? pm25.toFixed(1) : '—'}
          </span>
          <span className="font-mono uppercase text-[10px] tracking-wider text-stone-500">
            µg/m³
          </span>
        </div>

        {isLowConf && (
          <div className="font-mono text-[9px] uppercase text-stone-500 mt-1">
            · LOW CONFIDENCE · MAY BE UNRELIABLE
          </div>
        )}

        {!hasCell ? (
          <div className="mt-2 font-sans text-[11px] text-stone-500 leading-snug">
            Click a cell or search a zip to see local readings
          </div>
        ) : (
          <div className="mt-2 font-mono text-[10px] uppercase tracking-wider text-stone-500">
            EPA-corrected · IDW · {confidenceLabel(conf)} confidence
          </div>
        )}
      </div>

      {/* Section 3 — Who should take care */}
      {guidance && (
        <div className="mb-4">
          <SectionHeader>Who should take care</SectionHeader>
          <GuidanceList items={guidance.whoTakeCare} />
        </div>
      )}

      {/* Section 4 — Activity guidance */}
      {guidance && (
        <div className="mb-4">
          <SectionHeader>Activity guidance</SectionHeader>
          <GuidanceList items={guidance.activity} />
        </div>
      )}

      {/* Section 5 — Cell breakdown (cell-selected state only) */}
      {hasCell && (
        <div className="mb-4">
          <SectionHeader>Cell breakdown</SectionHeader>
          <dl className="text-[10px] font-mono uppercase">
            <div className="flex justify-between py-1">
              <dt className="text-stone-500">PM₂.₅ Max</dt>
              <dd className="text-stone-200">{cell.pm25Max.toFixed(1)} µg/m³</dd>
            </div>
            <div className="flex justify-between py-1">
              <dt className="text-stone-500">Confidence</dt>
              <dd className="text-stone-200">{confidenceLabel(cell.confidenceMin).toUpperCase()}</dd>
            </div>
            <div className="flex justify-between py-1">
              <dt className="text-stone-500">Latitude</dt>
              <dd className="text-stone-200">{cell.centerLat.toFixed(3)}</dd>
            </div>
            <div className="flex justify-between py-1">
              <dt className="text-stone-500">Longitude</dt>
              <dd className="text-stone-200">{cell.centerLon.toFixed(3)}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* Section 6 — Source / footer */}
      <div className="border-t border-hairline pt-3 mt-4">
        <div className="font-mono text-[9px] tracking-wider text-stone-500">
          Source:{' '}
          <a
            href={GUIDANCE_SOURCE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {GUIDANCE_SOURCE_LABEL}
          </a>
        </div>
      </div>
    </aside>
  );
}
