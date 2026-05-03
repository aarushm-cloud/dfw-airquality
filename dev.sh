#!/usr/bin/env bash
# dev.sh — start the AERIA dev stack with prefixed, multiplexed output.
#
# Usage:
#   ./dev.sh                                    # FastAPI backend only
#   ./dev.sh --with-streamlit                   # FastAPI + legacy Streamlit app
#   ./dev.sh --with-frontend                    # FastAPI + Vite dev server (AERIA frontend)
#   ./dev.sh --with-streamlit --with-frontend   # all three
#
# Ctrl+C cleanly terminates every child process.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Recursively kill a PID and every descendant. Process-group kills are
# unreliable here because some children (streamlit, uvicorn's reloader
# worker) detach into their own pgid; walking the tree via pgrep -P is
# the only approach that catches everything.
_kill_tree() {
  local pid=$1 sig=${2:-TERM} child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    _kill_tree "$child" "$sig"
  done
  kill -"$sig" "$pid" 2>/dev/null || true
}

WITH_STREAMLIT=0
WITH_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --with-streamlit) WITH_STREAMLIT=1 ;;
    --with-frontend)  WITH_FRONTEND=1 ;;
    -h|--help)
      grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# Always prefer the project venv when it exists. Don't gate on VIRTUAL_ENV —
# some shells inherit a stray VIRTUAL_ENV pointing at a system framework, and
# we want our pinned dependencies regardless.
if [[ -f "$ROOT/venv/bin/activate" && "${VIRTUAL_ENV:-}" != "$ROOT/venv" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/venv/bin/activate"
fi

PIDS=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[dev] shutting down (${#PIDS[@]} processes)..."
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid:-}" ]] && _kill_tree "$pid" TERM
  done
  # Fallback: streamlit re-parents its server process out of our subshell
  # tree, so the descendant walk can miss it. Match by command line —
  # patterns are unique to this project.
  pkill -TERM -f 'uvicorn api.main:app' 2>/dev/null || true
  pkill -TERM -f 'streamlit run app.py' 2>/dev/null || true
  pkill -TERM -f 'vite.*5173' 2>/dev/null || true
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid:-}" ]] && _kill_tree "$pid" KILL
  done
  pkill -KILL -f 'uvicorn api.main:app' 2>/dev/null || true
  pkill -KILL -f 'streamlit run app.py' 2>/dev/null || true
  pkill -KILL -f 'vite.*5173' 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Prefix every line of a child process's stdout/stderr with a tag so the
# multiplexed log stays scannable.
prefix() {
  local label="$1"
  local tag
  printf -v tag '[%s]' "$label"
  while IFS= read -r line; do
    printf '%s %s\n' "$tag" "$line"
  done
}

start_api() {
  echo "[dev] starting FastAPI on :8000"
  (uvicorn api.main:app --reload --port 8000 2>&1 | prefix api) &
  PIDS+=($!)
}

start_streamlit() {
  echo "[dev] starting Streamlit on :8501"
  (streamlit run app.py 2>&1 | prefix streamlit) &
  PIDS+=($!)
}

start_web() {
  if [[ ! -d "$ROOT/web/node_modules" ]]; then
    echo "[dev] web/node_modules not found — run 'cd web && npm install' first" >&2
    return 1
  fi
  echo "[dev] starting Vite on :5173"
  # nvm-installed node lives outside the default PATH; source it if available
  # so child shells can find `npm`. Harmless if nvm isn't present.
  if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    (cd "$ROOT/web" && bash -c 'source "$HOME/.nvm/nvm.sh" && npm run dev' 2>&1 | prefix web) &
  else
    (cd "$ROOT/web" && npm run dev 2>&1 | prefix web) &
  fi
  PIDS+=($!)
}

start_api
if [[ "$WITH_STREAMLIT" -eq 1 ]]; then
  start_streamlit
fi
if [[ "$WITH_FRONTEND" -eq 1 ]]; then
  start_web
fi

wait
