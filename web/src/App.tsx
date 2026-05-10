import { lazy, Suspense, useEffect } from 'react';
import { Loader, LoaderContent } from './components/Loader';
import { HealthBadge } from './components/ui/HealthBadge';
import { ZipSearch } from './components/ui/panels/ZipSearch';
import { CellInfoCard } from './components/ui/panels/CellInfoCard';
import { LeftPanel } from './components/ui/panels/LeftPanel';
import { TopStatusBar } from './components/ui/chrome/TopStatusBar';
import { TopNav } from './components/ui/chrome/TopNav';
import { BreadcrumbFooter } from './components/ui/chrome/BreadcrumbFooter';
import { StreetEmptyState } from './components/ui/overlays/StreetEmptyState';
import { FadeOverlay } from './components/ui/overlays/FadeOverlay';
import { useConnection } from './state/connection';
import { useGrid } from './state/grid';
import { useSensorsStore } from './state/sensors';
import { useViewStore } from './state/view';

const Scene = lazy(() =>
  import('./components/scene/Scene').then((m) => ({ default: m.Scene })),
);
const RouteLabPanel = lazy(() =>
  import('./components/ui/panels/RouteLabPanel').then((m) => ({
    default: m.RouteLabPanel,
  })),
);
const RouteStatsCard = lazy(() =>
  import('./components/ui/panels/RouteStatsCard').then((m) => ({
    default: m.RouteStatsCard,
  })),
);

const HEALTH_POLL_INTERVAL_MS = 5_000;

function App() {
  const poll = useConnection((s) => s.poll);
  const connectionStatus = useConnection((s) => s.status);
  const fetchGrid = useGrid((s) => s.fetchGrid);
  const gridStatus = useGrid((s) => s.status);
  const fetchSensors = useSensorsStore((s) => s.fetchSensors);
  const sensorsStatus = useSensorsStore((s) => s.status);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (!cancelled) poll();
    };

    tick();
    const id = setInterval(tick, HEALTH_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [poll]);

  useEffect(() => {
    if (connectionStatus !== 'ready') return;
    if (gridStatus === 'idle' || gridStatus === 'error') {
      fetchGrid();
    }
  }, [connectionStatus, gridStatus, fetchGrid]);

  useEffect(() => {
    if (connectionStatus !== 'ready') return;
    if (sensorsStatus === 'idle') {
      fetchSensors();
    }
  }, [connectionStatus, sensorsStatus, fetchSensors]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as { __stores: unknown }).__stores = {
      connection: useConnection,
      grid: useGrid,
      sensors: useSensorsStore,
      view: useViewStore,
    };
  }, []);

  // ESC exits street view. Bail out if focus is in an editable element so a
  // first ESC inside the zip search clears the input (input-level), and a
  // second ESC after blur exits the view. Matches every other web app.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      const isEditable =
        tag === 'input' ||
        tag === 'textarea' ||
        target?.isContentEditable === true;
      if (isEditable) return;
      if (e.key === 'Escape' && useViewStore.getState().view === 'street') {
        useViewStore.getState().setView('city');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <>
      <Loader />
      <Suspense fallback={<LoaderContent />}>
        <Scene />
      </Suspense>
      <LeftPanel />
      {/* Route Lab chunks load eagerly in parallel with main (Suspense
          wraps the component, not a view-state gate). On-demand loading
          would require lifting the view gate to App level — out of scope
          for item 6. The fallback is null because the components self-
          gate on view !== 'route' and render nothing in the common case. */}
      <Suspense fallback={null}>
        <RouteLabPanel />
      </Suspense>
      <TopStatusBar />
      <TopNav />
      <ZipSearch />
      <CellInfoCard />
      <Suspense fallback={null}>
        <RouteStatsCard />
      </Suspense>
      <BreadcrumbFooter />
      <StreetEmptyState />
      <FadeOverlay />
      <HealthBadge />
    </>
  );
}

export default App;
