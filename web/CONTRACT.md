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

## CORS contract
The backend allowlist is pinned to `http://localhost:5173`. If `VITE_API_BASE_URL`
changes, the backend's CORS config in `api/main.py` needs the matching origin
added before fetches will work in that environment.
