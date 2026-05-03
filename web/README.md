# AERIA · web

Vite + React + TypeScript + R3F frontend for the DFW Air Quality dashboard.

## Setup

```bash
cd web
npm install        # uses Node 20 (see .nvmrc)
npm run dev        # http://localhost:5173
```

## Env

Copy `.env.example` to `.env.local` to override the backend base URL:

```bash
cp .env.example .env.local
# then edit VITE_API_BASE_URL
```

Default points at `http://localhost:8000` (the FastAPI backend in `/api`).

## Recommended dev workflow

From the repo root, `./dev.sh --with-frontend` starts both the FastAPI
backend and this Vite dev server with prefixed, multiplexed logs and
clean Ctrl+C teardown.
