#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  start-pluto.sh — launch the Pluto dashboard from the repo root.
#
#  Starts both halves of Pluto for local dev:
#    - the API server   (python3 pluto/api/api.py, port 7700)
#    - the web dev server (yarn dev) at http://pluto.dev.localhost:5173/
#
#  The dev host is kept distinct from prod (pluto.localhost, via pluto/serve.sh)
#  so the browser password manager doesn't mix dev/prod DreameHome logins.
#  *.localhost resolves to loopback in the browser — no /etc/hosts needed.
#  Override the web port with VITE_PORT (use 80 + sudo for the bare URL).
#
#  Ctrl+C stops both. Run from anywhere — it locates its own dir.
#
#  Flags:
#    --api   start only the API (handy for backend / chat / bot testing)
#    --web   start only the web dev server
# ─────────────────────────────────────────────────────────────
set -euo pipefail

VITE_PORT="${VITE_PORT:-5173}"
DEV_HOST="pluto.dev.localhost"

# Resolve this script's own directory absolutely — robust whether invoked as
# ./start-pluto.sh, bash start-pluto.sh, or sh start-pluto.sh (no BASH_SOURCE).
SELF="${BASH_SOURCE[0]:-$0}"
ROOT="$(cd "$(dirname "$SELF")" && pwd)"
PLUTO="$ROOT/pluto"

WANT_API=1
WANT_WEB=1
case "${1:-}" in
  --api) WANT_WEB=0 ;;
  --web) WANT_API=0 ;;
  "")    ;;
  *)     echo "usage: ./start-pluto.sh [--api | --web]"; exit 1 ;;
esac

if [[ ! -f "$PLUTO/.env" ]]; then
  echo "[ERROR] $PLUTO/.env not found — copy pluto/.env.sample to pluto/.env first."
  exit 1
fi

pids=()
cleanup() { trap - INT TERM EXIT; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

if [[ "$WANT_API" == 1 ]] && lsof -nP -iTCP:7700 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> Pluto API already running on :7700 — leaving it; not starting a second one."
  WANT_API=0
fi

if [[ "$WANT_API" == 1 ]]; then
  # Prefer python3.11 — it's the interpreter that has pynput, which the Robutek
  # "Output → Emulator (Virtual Keyboard)" drive needs (the API synthesizes the
  # keys). api.py is pure stdlib, so any python3 runs it; 3.11 just unlocks drive.
  # (Run this from a terminal with Accessibility granted, or the keys are dropped.)
  PY=python3; command -v python3.11 >/dev/null 2>&1 && PY=python3.11
  echo "==> Pluto API   http://localhost:7700   ($PY)"
  ( cd "$PLUTO" && exec "$PY" api/api.py ) &
  pids+=($!)
fi

if [[ "$WANT_WEB" == 1 ]]; then
  echo "==> Pluto web   http://${DEV_HOST}:${VITE_PORT}/"
  ( cd "$PLUTO" && exec yarn dev --port "$VITE_PORT" --strictPort ) &
  pids+=($!)
fi

wait
