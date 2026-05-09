import { Line } from '@react-three/drei';
import { useRouteStore } from '../../../state/route';
import { latLonToWorld } from '../../../world/bbox';
import type { GeoJSONLineString } from '../../../api/client';

// Route polyline elevation: the cell floor sits at Y=0.01, hover at 0.02,
// selected ring at 0.03, building bases at 0.01 (growing in +Y). Routes
// render at 0.15/0.20 so they hover above the cell layer; in dense building
// blocks they'll be partially occluded by building geometry, which is
// acceptable — the visible portions in the gaps between building footprints
// are the "interesting" part of the path anyway. Cleanest is slightly higher
// than shortest so it wins on shared segments.
const SHORTEST_Y = 0.15;
const CLEANEST_Y = 0.20;

const SHORTEST_COLOR = '#888888';
const CLEANEST_COLOR = '#ffd166';

const SHORTEST_WIDTH = 1.6;
const CLEANEST_WIDTH = 2.6;

function geoToWorldPoints(
  geom: GeoJSONLineString,
  y: number,
): [number, number, number][] {
  return geom.coordinates.map(([lon, lat]) => {
    const { x, z } = latLonToWorld({ lat, lon });
    return [x, y, z];
  });
}

export function RoutePolylines() {
  const result = useRouteStore((s) => s.result);
  if (!result) return null;

  const shortest = geoToWorldPoints(result.shortest.geometry, SHORTEST_Y);
  const cleanest = geoToWorldPoints(result.cleanest.geometry, CLEANEST_Y);
  if (shortest.length < 2 || cleanest.length < 2) return null;

  return (
    <>
      <Line points={shortest} color={SHORTEST_COLOR} lineWidth={SHORTEST_WIDTH} />
      <Line points={cleanest} color={CLEANEST_COLOR} lineWidth={CLEANEST_WIDTH} />
    </>
  );
}
