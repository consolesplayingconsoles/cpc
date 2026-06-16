#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  start-pluto-lab.sh — launch the Pluto dashboard from the repo root.
#
#  Starts the local dev environment for Pluto:
#    - the API server   (python3 pluto/api/api.py, port 7700)
#    - the web dev server (yarn dev) at http://pluto.dev.localhost:5173/
#    - the API docs      (Swagger UI, dev-only, http://localhost:7800/)
#
#  The dev host is kept distinct from prod (pluto.localhost, via pluto/serve.sh)
#  so the browser password manager doesn't mix dev/prod DreameHome logins.
#  *.localhost resolves to loopback in the browser — no /etc/hosts needed.
#  Override the web port with VITE_PORT (use 80 + sudo for the bare URL).
#
#  Ctrl+C stops all of them. Run from anywhere — it locates its own dir.
#
#  Flags:
#    --api   start only the API + its Swagger docs (backend / chat / bot testing)
#    --web   start only the web dev server
# ─────────────────────────────────────────────────────────────
set -euo pipefail

VITE_PORT="${VITE_PORT:-5173}"
DEV_HOST="pluto.dev.localhost"

# Resolve this script's own directory absolutely — robust whether invoked as
# ./start-pluto-lab.sh, bash start-pluto-lab.sh, or sh start-pluto-lab.sh (no BASH_SOURCE).
SELF="${BASH_SOURCE[0]:-$0}"
ROOT="$(cd "$(dirname "$SELF")" && pwd)"
PLUTO="$ROOT/pluto"

WANT_API=1
WANT_WEB=1
case "${1:-}" in
  --api) WANT_WEB=0 ;;
  --web) WANT_API=0 ;;
  "")    ;;
  *)     echo "usage: ./start-pluto-lab.sh [--api | --web]"; exit 1 ;;
esac

if [[ ! -f "$PLUTO/.env" ]]; then
  echo "[ERROR] $PLUTO/.env not found — copy pluto/.env.sample to pluto/.env first."
  exit 1
fi

pids=()
cleanup() { trap - INT TERM EXIT; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

# Always restart the API so code edits actually take effect — a long-running
# server caches imported modules (controller.py etc.), so "leaving it running"
# silently serves stale code. Kill any existing one and start fresh.
if [[ "$WANT_API" == 1 ]]; then
  for P in 7700 7800; do
    OLD=$(lsof -ti:$P 2>/dev/null || true)
    if [[ -n "$OLD" ]]; then
      echo "==> :$P busy — restarting (kill $OLD) so edits take effect."
      kill $OLD 2>/dev/null || true
      for _ in $(seq 1 20); do lsof -ti:$P >/dev/null 2>&1 || break; sleep 0.2; done
    fi
  done
fi

if [[ "$WANT_API" == 1 ]]; then
  # Prefer the repo dev venv (.venv = Python 3.14 + pynput) — that's what unlocks
  # the Robutek "Output → Local Emulator (Virtual Keyboard)" drive (the API
  # synthesizes the keys). api.py is pure stdlib so any python3 runs it; the venv
  # just adds pynput. Create it once:
  #   python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
  # (Run from a terminal with Accessibility granted, or the synthesized keys drop.)
  PY=python3
  [[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
  echo "==> Pluto API   http://localhost:7700   ($PY)"
  ( cd "$PLUTO" && exec "$PY" api/api.py ) &
  pids+=($!)
fi

# Dev-only API docs (Swagger UI). Never deployed — see pluto/tools/swagger.py.
if [[ "$WANT_API" == 1 ]]; then
  echo "==> Pluto docs  http://localhost:7800   (Swagger UI, dev-only)"
  ( cd "$PLUTO" && exec "$PY" tools/swagger.py ) &
  pids+=($!)
fi

if [[ "$WANT_WEB" == 1 ]]; then
  echo "==> Pluto web   http://${DEV_HOST}:${VITE_PORT}/"
  ( cd "$PLUTO" && exec yarn dev --port "$VITE_PORT" --strictPort ) &
  pids+=($!)
fi

wait
