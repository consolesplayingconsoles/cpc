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

# Source shell profile so the correct python3 is on PATH regardless of
# whether this is called from SSH, tmux, or the local terminal.
[ -f ~/.bashrc ]  && source ~/.bashrc  2>/dev/null || true
[ -f ~/.profile ] && source ~/.profile 2>/dev/null || true

# Remember where we were invoked from (to resolve relative env-file args), then
# run relative to this script's own dir (pluto-python-tui/) so client paths hold.
ORIG_PWD="$PWD"
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
  # A relative arg is relative to the caller's dir, not this client dir.
  [[ "$ENV_FILE" != /* ]] && ENV_FILE="$ORIG_PWD/$ENV_FILE"
else
  # No argument: auto-detect the sole console env. Console dirs sit one level up
  # from this client dir; only the target <console>/.env ships on deploy.
  shopt -s nullglob
  CANDIDATES=()
  for f in ../*/.env; do
    [[ "$f" == ../pluto/.env ]] && continue
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

# ── Python selection ─────────────────────────────────────────
# Prefer an explicit versioned binary so a stale system python3 doesn't
# shadow the freshly compiled one.
if   command -v python3.6 >/dev/null 2>&1; then PY=python3.6
elif command -v python3.7 >/dev/null 2>&1; then PY=python3.7
elif command -v python3.8 >/dev/null 2>&1; then PY=python3.8
elif command -v python3   >/dev/null 2>&1; then PY=python3
else
  echo "  [ERROR] no python3 found" && exit 1
fi

if ! $PY -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 6) else 1)'; then
  PYV="$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  echo "  [ERROR] Python ${PYV} is too old — needs 3.6+" && exit 1
fi

exec env PYTHONPATH=vendor COLORTERM=truecolor $PY main.py "$ENV_FILE"
