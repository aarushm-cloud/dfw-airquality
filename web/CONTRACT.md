# AERIA Frontend Contract

Conventions established in Session 2. Future sessions follow these or explicitly diverge with reasoning.

## Where things live
- Design tokens: `tailwind.config.js` (colors, fonts) — do not rename existing tokens
- API client: `src/api/client.ts` — one function per endpoint
- State: `src/state/{domain}.ts` — Zustand stores, one per domain
- Components: `src/components/`
- Scene components: `src/components/scene/` — anything that lives inside the R3F `<Canvas>`
- World math: `src/world/bbox.ts` — single source of truth for coordinate transforms

## Coordinate system

**Read this before touching anything in `src/components/scene/` or adding spatial features.**

Canonical implementation: [`src/world/bbox.ts`](src/world/bbox.ts). Import every constant and helper from there — do not reinvent.

### World-space axes (right-handed, Y-up — R3F default)
- **X:** longitude direction. East is `+X`, west is `-X`.
- **Z:** latitude direction. **North is `-Z`**, south is `+Z`. This matches map convention: from a top-down camera view, north reads as "up" on screen.
- **Y:** vertical. Ground plane sits at `Y=0`. Cell grid sits at `Y=0.01`. Hover highlight at `0.02`, selected at `0.03`.

### Cell-grid orientation
- 30 × 30 = **900 cells** covering the Dallas bbox.
- **Row 0 = southernmost row, row 29 = northernmost.**
- **Col 0 = westernmost col, col 29 = easternmost.**
- Storage is row-major: `cells[row * 30 + col]`.
- The source `/api/grid` array uses `pm25[latIdx][lonIdx]` with `lats[0]=south`, `lons[0]=west`. So **row maps directly to latIdx and col maps directly to lonIdx — no flip needed.**

### Cosine correction (locked, do not "fix")
At the Dallas reference latitude (`REF_LAT_DEG = 32.78°N`), one degree of longitude is only `~0.840` of one degree of latitude in physical-distance terms. `LON_CORRECTION = cos(32.78°) ≈ 0.8408` is applied wherever a longitude span is converted to world units.

The visible consequence: the world grid is `~28.05 × 30` units in world space (slightly taller than wide), and individual cells are `CELL_X ≈ 0.9359 × CELL_Z = 1.0` world units. **Cells are square in physical-distance terms but slightly rectangular in world-units terms.** This is correct and matches `engine/interpolation.py`. Do not stretch the X axis to "make cells square in world space" — that would re-introduce the very distortion the cosine correction exists to remove.

### Helpers (use these, don't roll your own)
- `cellToLatLon({row, col}) → {lat, lon}` — center of the cell
- `latLonToWorld({lat, lon}) → {x, z}` — world-space position
- `cellToWorld({row, col}) → {x, z}` — composition of the above two
- `latLonToCell({lat, lon}) → {row, col} | null` — inverse, returns `null` outside the bbox

A dev-only round-trip assertion runs at module load and console.asserts that `cell → latlon → cell` is identity for the four corners and the centre. If you ever see `[bbox] round-trip failed` in the console, the math is broken — fix before doing anything else.

## Patterns
- Polling: single `setInterval` with cleanup, idempotent under StrictMode
- Env: `VITE_API_BASE_URL` with fallback to `localhost:8000`, logged at module load
- No green in the palette. Status indicators use gold/teal/stone from locked tokens.
- Hover state in the scene is `useRef`-based to avoid 60Hz re-renders. Selected state is React/Zustand state because clicks are infrequent.
- Per-cell rendering uses one `<instancedMesh>` of 900 instances (R3F supports raycasting against instanced meshes natively via `e.instanceId`). Don't render 900 individual meshes.
- Cells use `MeshBasicMaterial` (unlit) so all 900 stay visually consistent. Buildings use `MeshStandardMaterial` with `flatShading` so they pick up the directional light and read as concrete. The lit/unlit split is the right division.

## Buildings

Implementation: [`src/world/buildings.ts`](src/world/buildings.ts) (deterministic generator) + [`src/components/scene/Buildings.tsx`](src/components/scene/Buildings.tsx) (R3F instanced mesh).

### Density rule (locked)
Procedural noise + radial bias + low-frequency separation. **No AQI / PM₂.₅ input.** No real geography. No hand-tagged districts. The signature shape is a dense centre that fades toward the bbox edges, broken into 3–5 distinct city clusters by a low-frequency noise modulator that carves "valleys" between them.

```
density(row, col) = (radial * 0.7 + local * 0.3 + radial * local * 0.4) * separation
  radial      = exp(-distFromOrigin / 6.5)            // soft radial falloff
  local       = noise01(row * 0.35, col * 0.35)       // ~3–6 cell clusters
  separation  = 0.4 + 0.6 * noise01(row * 0.08, col * 0.08)  // city gaps
```

Density bins to per-cell building count: `<0.18 → 0`, `<0.40 → 1`, `<0.70 → 2`, else 3. Empty cells are intentional and form the gaps between cities — they remain hover/click targets via the underlying `CellGrid` instanced mesh.

Distribution gate (run in `/tmp/gen_smoke.mjs` or equivalent before any density-rule change):
- Total buildings in 400–1500
- Mean height in 0.8–1.6 world units
- Per-cell density falls off radially (downtown > suburbs)

### Material + shading
`MeshStandardMaterial({ color: '#7a7480', roughness: 0.85, metalness: 0, flatShading: true })`. Flat shading is intentional — smooth-shaded boxes look like polished plastic; flat-shaded boxes read as concrete. Don't smooth-shade them.

### Geometry + scaling
One unit `BoxGeometry(1,1,1)` reused across all instances. Each instance scales independently to `(width, height, depth)`. Per-instance footprint:

```
footprintFrac = 0.32 + 0.23 * (1 - min(height, 2.5) / 2.5)   // 0.32–0.55 of the cell
width  = footprintFrac * CELL_X
depth  = footprintFrac * CELL_Z
```

Result: ~30% of the cell area is occupied by the building, the rest stays visible for cell hover/click feedback.

### Y placement
Building centers at `Y = 0.01 + height/2`, so the base sits flush with the cell plane (Y=0.01) and growth is in `+Y`. Cell hover (Y=0.02) and selected ring (Y=0.03) clip into the base of buildings — that's intentional: hover/selected mark *cells*, not buildings.

### Pointer events
Buildings do **not** intercept raycasts. The `<instancedMesh>` in `Buildings.tsx` sets `raycast={() => null}` so clicks pass through to the cell underneath. Cells own the click target. Don't change this without also reworking the click flow.

### Selected ring overflow
The selected-cell highlight in `CellGrid` is sized at `1.04 * CELL_INSET` so the gold ring extends slightly past the building's footprint and stays visible on all four sides even when a tall building sits on the cell. Hover stays at `0.96 * CELL_INSET` so it never bleeds into neighbouring cells.

### Determinism
Generator is seeded via the LCG in `src/world/noise.ts` (`PRNG(0xae12a)`). The city is identical across reloads. Don't change the seed without intent — it'll redraw the entire skyline. Don't switch to `Math.random()`.

## Camera

Initial position: `[0, 38, 0.1]` — essentially top-down. Centers the full grid in the viewport at ~93% fill on a 16:9 display. The tiny Z offset keeps OrbitControls' "up" direction defined so dragging-to-tilt works on the first frame. `minPolarAngle: 0` allows users to rotate back to top-down.

`enablePan: false` — the city stays anchored at world origin. Panning was disabled because it let users drift the whole grid off-center, breaking the cell-to-cell mental map. Don't re-enable without a strong reason.

`minDistance: 4` lets users zoom right down to a few-cell cluster. `maxDistance: 60` is paired with fog `far: 90` (always keep `maxDistance < fogFar` with margin).

## Quirks

### npm install requires `--legacy-peer-deps`
`@react-three/fiber@8` declares `react-native`, `expo`, `expo-gl`, and similar
as non-optional peer dependencies. Modern npm tries to resolve them, which
pulls React 19 and conflicts with our locked React 18.3.

To install any new package in `web/`:

```bash
npm install --legacy-peer-deps <package>
```

This applies to all dependency additions in this directory until R3F v9 ships.

### Vite host binding on macOS
`vite.config.ts` sets `host: '127.0.0.1'`, but on macOS with default
`/etc/hosts`, Vite ends up listening on `::1` (IPv6 localhost) regardless.
Functionally fine because `http://localhost:5173` resolves correctly and the
backend's CORS allowlist includes both `localhost:5173` and `127.0.0.1:5173`.
Don't try to "fix" the host binding — it's an OS-level resolution quirk, not
a Vite bug.

### Canvas is `pointer-events-auto`, not `none`
Session 2 set the Canvas to `pointer-events-none` because there was nothing
inside it to click. Session 3a flipped it to `pointer-events-auto` because
cells are clickable. Future overlays that float on top of the Canvas must
either set `pointer-events-none` themselves or rely on z-index — the Canvas
no longer transparently passes events through to the DOM behind it.

### Static instance matrices, no DynamicDrawUsage
`CellGrid` writes the 900 cell matrices once in `useLayoutEffect` and never
mutates them; the default static draw usage is correct. Sessions that add
*moving* instances (e.g. Session 3c particles) must explicitly call
`instanceMatrix.setUsage(THREE.DynamicDrawUsage)` on their own meshes — do
not change the default for `CellGrid`.

## Future cleanup

Items intentionally deferred. Address when the upstream condition is met.

- **Drop `--legacy-peer-deps`** once `@react-three/fiber@9` ships with proper
  React 18/19 dual peers. No tracking issue; grep for `legacy-peer-deps` in
  this file when revisiting.
- **Code-split the Three.js bundle.** Currently ~265 KB gzipped, triggers
  Vite's >500 KB bundle warning. Wait until Session 3 introduces dynamically
  loadable scene chunks before splitting — splitting an empty scene saves
  nothing.
- **Deterministic screenshot baselining.** `web/docs/session-2-ready.png` is
  currently captured manually. A small Playwright script in `web/scripts/`
  would make baselines reproducible. Defer until visual regressions become
  a real problem.
- **Building shadows.** Currently disabled. Adding shadow maps means tuning
  the directional light's shadow camera frustum to cover the whole grid plus
  bias to avoid acne — real work, not the point of 3b. Defer until a polish
  pass after the full UI is in.
- **Procedural roads (Session 3b.5).** Faint emissive highway lines along
  ~every 5th cell axis on the ground plane, plus a road-exclusion zone in
  `buildings.ts` so no building spawns within ~0.15 cells of a road. Should
  land before Session 3c so roads inform particle spawn patterns.
- **Per-building rooftop slots for 3c+.** The `Building` type already carries
  `row`/`col`. If 3c ever wants particles to spawn from rooftops, the
  generator already gives every consumer the data it needs.

## CORS contract
The backend's allowlist is built from two sources:

1. Always-included localhost dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`)
2. Comma-separated extras from the `AERIA_CORS_ORIGINS` env var

To deploy: set `AERIA_CORS_ORIGINS` on the backend host to include the
production frontend origin (e.g. `https://aeria.vercel.app`). Local dev needs
no env var.

If `VITE_API_BASE_URL` changes on the frontend, the matching origin must be
added to `AERIA_CORS_ORIGINS` on the backend or fetches will fail with CORS
errors.
