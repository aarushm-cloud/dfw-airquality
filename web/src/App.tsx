import { useEffect } from 'react';
import { Scene } from './components/Scene';
import { HealthBadge } from './components/HealthBadge';
import { useConnection } from './state/connection';

const HEALTH_POLL_INTERVAL_MS = 5_000;

function App() {
  const poll = useConnection((s) => s.poll);

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

  return (
    <>
      <Scene />
      <HealthBadge />
    </>
  );
}

export default App;
