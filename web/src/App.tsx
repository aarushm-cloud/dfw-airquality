import { useEffect } from 'react';
import { Scene } from './components/Scene';
import { HealthBadge } from './components/HealthBadge';
import { ZipSearch } from './components/ui/ZipSearch';
import { CellInfoCard } from './components/ui/CellInfoCard';
import { LeftPanel } from './components/ui/LeftPanel';
import { TopStatusBar } from './components/ui/TopStatusBar';
import { TopNav } from './components/ui/TopNav';
import { BreadcrumbFooter } from './components/ui/BreadcrumbFooter';
import { useConnection } from './state/connection';
import { useGrid } from './state/grid';
import { useSensorsStore } from './state/sensors';

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
    };
  }, []);

  return (
    <>
      <Scene />
      <LeftPanel />
      <TopStatusBar />
      <TopNav />
      <ZipSearch />
      <CellInfoCard />
      <BreadcrumbFooter />
      <HealthBadge />
    </>
  );
}

export default App;
