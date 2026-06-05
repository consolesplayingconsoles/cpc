#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  run.sh — stop any running instance and start the console app
#
#  Usage: ./run.sh [path-to-env-file]
#  Example: ./run.sh wii/.env
#
#  On a deployed console there is exactly one console directory, so the
#  env file can be omitted — it is auto-detected and started directly.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# Always run relative to this script's own directory so paths stay
# correct whether called directly or via SSH.
cd "$(dirname "$0")"

if [[ $# -gt 1 ]]; then
  echo ""
  echo "  Usage: ./run.sh [env-file]"
  echo "  Example: ./run.sh wii/.env"
  echo ""
  exit 1
fi

if [[ $# -eq 1 ]]; then
  ENV_FILE="$1"
else
  # No argument: auto-detect the sole console env (every sibling except
  # pluto is stripped on deploy, so only one <console>/.env should exist).
  shopt -s nullglob
  CANDIDATES=()
  for f in */.env; do
    [[ "$f" == pluto/.env ]] && continue
    CANDIDATES+=("$f")
  done
  if [[ ${#CANDIDATES[@]} -eq 1 ]]; then
    ENV_FILE="${CANDIDATES[0]}"
  elif [[ ${#CANDIDATES[@]} -eq 0 ]]; then
    echo ""
    echo "  [ERROR] no <console>/.env found — pass one explicitly: ./run.sh wii/.env"
    echo ""
    exit 1
  else
    echo ""
    echo "  [ERROR] multiple console envs found (${CANDIDATES[*]})"
    echo "          pass one explicitly: ./run.sh wii/.env"
    echo ""
    exit 1
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo ""
  echo "  [ERROR] env file not found: $ENV_FILE"
  echo ""
  exit 1
fi

pkill -f 'python3 main.py' || true

mkdir -p logs
nohup env PYTHONPATH=vendor python3 main.py "$ENV_FILE" \
  </dev/null >logs/cpc.log 2>&1 &

echo "  started (PID $!)"
echo "  logs: $(pwd)/logs/cpc.log"
