import { CityScene } from './city/CityScene';
import { StreetScene } from './street/StreetScene';
import { useViewStore } from '../../state/view';

// View-agnostic infrastructure (background color, fog) lives here so the
// transition between scenes inherits it for free. Anything view-specific —
// camera, controls, lighting — lives inside the respective scene component.
export function SceneRoot() {
  const view = useViewStore((s) => s.view);

  return (
    <>
      <color attach="background" args={['#0a0a0f']} />
      <fog attach="fog" args={['#0a0a0f', 35, 90]} />

      {/* 'city' and 'route' both render the city scene — Route Lab adds
          <RoutePolylines/> as an overlay inside CityScene without unmounting
          it, so the OrbitControls handle and camera snapshot stay live. */}
      {view === 'street' ? <StreetScene /> : <CityScene />}
    </>
  );
}
