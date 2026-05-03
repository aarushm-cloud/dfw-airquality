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
- Cells use `MeshBasicMaterial` (unlit) so all 900 stay visually consistent. Buildings (Session 3b) will be lit; that contrast is the right division.

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
