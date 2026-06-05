#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  start.sh — run API + Vite dev server with labeled output
#  Ctrl-C (or any signal) stops both processes cleanly.
# ─────────────────────────────────────────────────────────────
set -uo pipefail

CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RESET='\033[0m'

API_PID=""
VITE_PID=""

cleanup() {
  echo ""
  [[ -n "$API_PID" ]]  && kill "$API_PID"  2>/dev/null || true
  [[ -n "$VITE_PID" ]] && kill "$VITE_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Prefix every output line with a colored label; color spans the full line.
prefix() {
  local label="$1" color="$2"
  while IFS= read -r line; do
    printf "${color}%s  %s${RESET}\n" "$label" "$line"
  done
}

export PYTHONUNBUFFERED=1

for PORT in 7700 5173; do
  OLD_PID=$(lsof -ti:$PORT 2>/dev/null || true)
  if [[ -n "$OLD_PID" ]]; then
    kill "$OLD_PID" 2>/dev/null || true
    while lsof -ti:$PORT &>/dev/null; do sleep 0.1; done
  fi
done

python3 api/api.py                     > >(prefix "[api] " "$CYAN")   2>&1 & API_PID=$!
npm run dev -- --clearScreen false     > >(prefix "[vite]" "$YELLOW") 2>&1 & VITE_PID=$!

wait
