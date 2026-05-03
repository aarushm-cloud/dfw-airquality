# AERIA Frontend Contract

Conventions established in Session 2. Future sessions follow these or explicitly diverge with reasoning.

## Where things live
- Design tokens: `tailwind.config.js` (colors, fonts) — do not rename existing tokens
- API client: `src/api/client.ts` — one function per endpoint
- State: `src/state/{domain}.ts` — Zustand stores, one per domain
- Components: `src/components/`

## Patterns
- Polling: single `setInterval` with cleanup, idempotent under StrictMode
- Env: `VITE_API_BASE_URL` with fallback to `localhost:8000`, logged at module load
- No green in the palette. Status indicators use gold/teal/stone from locked tokens.
- Canvas wrappers are `pointer-events-none`; overlays opt back in.

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
