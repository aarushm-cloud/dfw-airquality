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

## UI chrome

DOM-side UI components live in `src/components/ui/`. R3F scene components live in `src/components/scene/`. Don't mix the two trees — DOM children can't render inside the Canvas, and scene children can't render outside it.

### Floating panels
- Absolute positioned, `z-20+`, `pointer-events-auto`
- Container chrome: `bg-ink-900/85`+ with backdrop blur, hairline borders, `rounded-sm`
- Gold (`#ffd166`) is the active-state accent (focus rings, selected). AQI colors are reserved for AQI signal. The single legal exception is the AQI category dot in panels, where the dot's color literally is the AQI signal restated.
- Typography: Fraunces serif for primary numerics (the big PM₂.₅ value); JetBrains Mono uppercase for metadata, status labels, and ID-like strings; Inter Tight for body text.

### Selection state
- Lives in the grid store ([`src/state/grid.ts`](src/state/grid.ts)) — `selectedCellRow`, `selectedCellCol`, `selectedCellMeta`
- All selection paths route through `selectCellByCoord(row, col, { pan? })` or `selectCellByZip(zip)`. Don't write to the selection fields directly
- `pan` defaults to `false`. Click and future pin paths leave the camera alone; only explicit-search paths opt in with `{ pan: true }`. Future selection paths should default to no-pan unless there's a clear reason
- `clearSelection()` invalidates the selection token and clears the meta — call this from any close/dismiss UI
- Async selection uses a monotonically increasing request token. In-flight zip resolutions check `token === _selectionToken` before writing back, so fast successive selections never flicker stale data

### Cross-canvas handles
- OrbitControls and the active camera are registered into [`useSceneStore`](src/state/scene.ts) by `SceneRoot` on mount. DOM-side panners read from the store rather than threading refs through props
- `SceneRoot`'s effect MUST clear the handles on unmount. Without the cleanup, HMR or scene remount leaves stale handles pointing at a destroyed Three camera, and the next pan crashes
- Camera pan utility lives in [`src/components/scene/cameraPan.ts`](src/components/scene/cameraPan.ts). It returns a cancel fn so a follow-up pan can abort an in-flight animation

### Left panel ([`src/components/ui/LeftPanel.tsx`](src/components/ui/LeftPanel.tsx))
- Width **280px** (constant `PANEL_WIDTH_PX` in the same file). Full-height, left-edge, fixed positioning
- Six sections, top to bottom: header / status / who-should-take-care / activity guidance / cell breakdown / source-footer
- Health guidance content is sourced from EPA AirNow Activity Guide (Feb 2023) and lives in [`src/world/healthGuidance.ts`](src/world/healthGuidance.ts). Do not edit, paraphrase, or extend the strings — they're authored from a public health source and changes are not in scope
- Source attribution link in the footer is mandatory for credibility
- Cell breakdown section renders only when a cell is selected. Layout is a key/value `<dl>`, not tile grid — at 240px content width tiles are unworkably small
- Panel is the load-bearing reference for chrome layout. **`PANEL_WIDTH_PX + 16` is the locked left offset for `ZipSearch`** ([`src/components/ui/ZipSearch.tsx`](src/components/ui/ZipSearch.tsx)) — keep them in sync if the panel ever gets wider
- Selector hooks (`useSelectedCell`, `useSelectedCellMeta`, `useMetroAggregates`, `useSearchedZip`) read primitives off the grid store and `useMemo` over them. Derived values (`cellsByCoord`, `metro`) are computed once in `fetchGrid` and stored as stable references — **NOT** computed in selectors. This is a perf requirement: panel + info card + breadcrumb all consume the same hooks, and selector-side derivation would re-run on every store update and rebuild every consumer

### Top status bar ([`src/components/ui/TopStatusBar.tsx`](src/components/ui/TopStatusBar.tsx))
- Top-right, `top:16 right:16`. **Portal pattern required** (right-edge compositor) — `createPortal(..., document.body)` + `transform: translateZ(0)` + `isolate` + `zIndex: 2147483000`. Same recipe as `CellInfoCard`. Don't try without and discover the symptom
- Live indicator (gold pulsing dot) + sensor count + metro PM₂.₅ + UPDATED timestamp
- **Wind metric is HIDDEN** because `/api/sensors` does not expose wind speed or direction at metro level. To enable: backend must add `wind_speed_mps` and `wind_deg` (or equivalent) to the top-level `/api/sensors` response, then re-add the metric block + leading separator in `TopStatusBar.tsx`. See future-cleanup
- UPDATED relative-time formatter ticks every 30s via a single `useEffect`+`setInterval` with cleanup — idempotent under StrictMode. The 30s timer triggers re-renders only, never network requests
- Metro AQI dot uses **6px** (`h-1.5 w-1.5`); panel and info card use **8px** (`h-2 w-2`). The smaller dot in the status bar lets it recede into the metric row's typographic density

### Top nav ([`src/components/ui/TopNav.tsx`](src/components/ui/TopNav.tsx))
- Top-center, `top-4 left-1/2 -translate-x-1/2 z-20`. Plain absolute positioning — no portal pattern needed (left/center surfaces have stayed visible without it)
- Four tabs: City overview (active), Street view, Time machine, Route lab — three disabled
- Active tab uses **gold underline** (`border-b-2 border-gold`) on `bg-ink-800`. Gold = active-state accent, never AQI
- Disabled tabs use the **accessible-disabled pattern** — `aria-disabled="true"` + `cursor-not-allowed` + `onClick={e => e.preventDefault()}`. NOT native `<button disabled>`, because native disabled silently swallows pointer events on some browsers and tooltips never fire on hover or keyboard focus
- Tooltip uses both `group-hover:opacity-100` AND `group-focus-within:opacity-100`, so the hint surfaces on either interaction modality

### Breadcrumb footer ([`src/components/ui/BreadcrumbFooter.tsx`](src/components/ui/BreadcrumbFooter.tsx))
- Full-width, `bottom-0 left-0 right-0 z-10 pointer-events-none`
- Left side: nav path (`AERIA.ATLAS > DFW > CITY OVERVIEW [> CELL r·c · ZIP zzzzz]`). Right side: build metadata
- Build metadata: BBOX from [`src/world/bbox.ts`](src/world/bbox.ts), version from `package.json` via JSON import (Vite resolves natively — no `resolveJsonModule` flag needed under `moduleResolution: bundler`)
- Separator style: ` · ` (dot-bullet, spaced) consistent across both sides; coordinate slashes inside the BBOX chunk are intentional (it's a tuple, not a list)
- Resolves the cell ZIP only — **typed-zip disclosure is in the info card, not the breadcrumb**. The breadcrumb is ground-truth navigation state, not interaction artifact. Don't extend disclosure here

### Disclosure rule (75025/75023 case)
- 75025 (zip code) maps to a cell whose reverse-geocoded ZIP is something else (75024 / Plano boundary)
- The info card discloses the mismatch as `ZIP <resolved> (you typed <searched>)` — fires only when **typed zip ≠ resolved zip**
- Do **not** extend this to disclose cell-index mismatches — would introduce noise without signal
- The left panel and breadcrumb show the **resolved zip only** (no parenthetical) — those surfaces are ground-truth navigation state. Disclosure stays in the interaction-driven info card

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

### Floor tint opacity uses a squared confidence curve
[`src/components/scene/CellFloorTint.tsx`](src/components/scene/CellFloorTint.tsx) maps confidence to opacity via `0.05 + conf² × 0.35`. Real-world confidence clusters between 0.5 and 1.0; the squared curve gives visible separation between high-confidence (downtown, ~0.40 alpha) and low-confidence (south/east edges, ~0.05 alpha) cells. A linear curve compressed everything into the high end and made the signal invisible.

### No red/green/orange/yellow/purple in chrome
The chrome rule has one legal exception: AQI category dots in the panel, info card, and status bar — the dot's color literally restates the AQI signal. Everywhere else (text, borders, surfaces, tooltips, error states), use stone/gold/teal from the locked palette. Even error states use stone-300, never red.

### 75025/75023 disclosure scope
Disclosure fires only on **zip mismatch** (typed zip ≠ reverse-geocoded zip), and only in the cell info card. Future engineers might be tempted to extend this to cell-level differences — don't. The breadcrumb and left panel show resolved-zip only; that's the ground-truth navigation state surface.

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
- **"Drop into street" button** is a placeholder until Session 6 wires the
  street-drop-in scene. Tooltip reads "Available in Session 6".
- **"Pin" feature** is deferred. Will need a pinned-cells store + persistence.
  Tooltip reads "Coming soon".
- **Camera-pan offset preservation is Cartesian.** With the locked top-down
  camera this is fine (offset is mostly a vertical Y delta). After a future
  retune to an isometric camera, switch to spherical-relative offset
  preservation in [`cameraPan.ts`](src/components/scene/cameraPan.ts) so pans
  don't drift the polar angle.
- **Keyboard shortcut for the search bar** (e.g. `/` to focus the input) is
  unscoped — add when keyboard nav becomes a usability ask.
- **Cell breakdown — extra stats.** Traffic adjustment, wind adjustment,
  highway distance from `DESIGN_NOTES.md` are not in the breakdown list.
  Requires `/api/cells/at` to return per-cell traffic / wind / highway-distance
  derived metrics. Backend session.
- **Status bar wind metric.** Currently hidden because `/api/sensors`
  exposes no wind fields at metro level. To enable: backend adds
  `wind_speed_mps` + `wind_deg` (or equivalent) to the top-level
  `/api/sensors` response, then re-add the metric block + leading separator
  in `TopStatusBar.tsx`. Backend session.
- **Bottom timeline scrubber** for historical playback (Time Machine view) —
  Phase 7+, deferred from Session 5.
- **Cell-vs-metro delta on the panel.** Originally specced as a Δ vs metro
  line; cut because comparing positive/negative deltas requires color or
  directional framing that conflicts with the no-red/green chrome rule.
- **Top chrome row not responsive below 1500px.** At 1366×768 the top nav,
  status bar, and zip search begin to overlap. Accepted limit for v1
  (desktop-first); revisit when responsive becomes a real ask.
- **Low-confidence threshold (0.4) is empirical.** Chosen visually before the
  ML model lands. Revisit when Phase 4 model produces calibrated
  confidence distributions.
- **Backend cache `/api/health` chicken-and-egg.**
  [`api/routes/health.py`](../api/routes/health.py) reports `cache_warm`
  based on `_grid_cache["value"] is not None`, but the cache is filled
  lazily by the first `/api/grid` request — and the frontend's connection
  store gates that fetch on `cache_warm === true`
  ([`src/state/connection.ts`](src/state/connection.ts), [`src/App.tsx`](src/App.tsx)).
  On cold boot the page hangs forever in `'warming'` until something hits
  `/api/grid` directly. Workaround during dev:
  `curl http://localhost:8000/api/grid > /dev/null`. Real fix: trigger a
  warm-up fetch on FastAPI lifespan startup so the cache is populated
  before the first health probe. Backend session.
- **Backend `/api/grid` cache instability under load.** Even with
  `cache_warm: true` reported, the same endpoint has been observed
  responding in 116ms then 40s on subsequent hits in the same session,
  suggesting cache eviction. When the cache evicts mid-session, the page
  silently empties (cells go to default zeros, particles disappear) until a
  hard refresh re-seeds. Real fix: backend should self-warm on a
  TTL-aware schedule, or the frontend connection gate should not require
  `cache_warm` once it's seen `'ready'` at least once. Backend session.

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
