#!/usr/bin/env bash
# dev.sh — start the AERIA dev stack with prefixed, multiplexed output.
#
# Usage:
#   ./dev.sh                    # FastAPI backend only
#   ./dev.sh --with-streamlit   # FastAPI + legacy Streamlit app side-by-side
#
# Phase 6 Session 2+ will add a Vite dev server here (see TODO below).
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
for arg in "$@"; do
  case "$arg" in
    --with-streamlit) WITH_STREAMLIT=1 ;;
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
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid:-}" ]] && _kill_tree "$pid" KILL
  done
  pkill -KILL -f 'uvicorn api.main:app' 2>/dev/null || true
  pkill -KILL -f 'streamlit run app.py' 2>/dev/null || true
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

# TODO (Session 2+): start Vite dev server here once web/ exists.
# start_web() {
#   echo "[dev] starting Vite on :5173"
#   (cd web && npm run dev 2>&1 | prefix web) &
#   PIDS+=($!)
# }

start_api
if [[ "$WITH_STREAMLIT" -eq 1 ]]; then
  start_streamlit
fi
# start_web   # uncomment in Session 2

wait
