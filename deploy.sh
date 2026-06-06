#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — build locally and ship to a console node via SSH
#  (With local localhost SSH simulation fallback)
#
#  Usage: ./deploy.sh <path-to-env-file>
#  Example: ./deploy.sh wii/.env
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Args ──────────────────────────────────────────────────────
if [[ $# -ne 1 ]]; then
  echo ""
  echo "  Usage: ./deploy.sh <env-file>"
  echo "  Example: ./deploy.sh wii/.env"
  echo ""
  exit 1
fi

ENV_FILE="$1"

if [[ ! -f "$ENV_FILE" ]]; then
  echo ""
  echo "  [ERROR] env file not found: $ENV_FILE"
  echo ""
  exit 1
fi

# ── Parse env file ────────────────────────────────────────────
_env_get() {
  local key="$1" val=""
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in
      "${key}="*)
        val="${line#*=}"
        val="${val#\"}" ; val="${val%\"}"
        val="${val#\'}" ; val="${val%\'}"
        break ;;
    esac
  done < "$ENV_FILE"
  echo "$val"
}

HOST_IP="$(_env_get HOST_IP)"
NODE_NAME="$(_env_get NODE_NAME)"
CUSTOM_SSH_ALIAS="${CUSTOM_SSH_ALIAS:-$(_env_get CUSTOM_SSH_ALIAS)}"
SSH_USER="${SSH_USER:-$(_env_get SSH_USER)}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$(_env_get SSH_KEY_PATH)}"

if [[ -z "$HOST_IP" || -z "$NODE_NAME" ]]; then
  echo ""
  echo "  [ERROR] Missing required fields in $ENV_FILE"
  echo ""
  exit 1
fi

REMOTE_PATH="/opt/cpc"
CONSOLE_DIR=$(basename "$(dirname "$ENV_FILE")")

# ── Check for Local Simulation Mode ───────────────────────────
if [[ "$HOST_IP" == "localhost" || "$HOST_IP" == "127.0.0.1" ]]; then
  echo ""
  echo "  [SIMULATION] Intercepting network path for localhost deployment."
  echo "  ── Deploying to ${NODE_NAME} (SIMULATED) ──"
  echo ""
  echo "  [1/2] Vendoring dependencies..."
  pip install --disable-pip-version-check -r requirements.txt --target=vendor/ --quiet
  echo "        done."

  echo "  [2/2] Syncing files to ${REMOTE_PATH}..."
  mkdir -p ${REMOTE_PATH}/logs
  echo "        done."

  exit 0
fi

# ── Build SSH primitives ───────────────────────────────────────
if [[ -n "$CUSTOM_SSH_ALIAS" ]]; then
  SSH="ssh ${CUSTOM_SSH_ALIAS}"
else
  SSH="ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no ${SSH_USER}@${HOST_IP}"
fi

echo ""
echo "  ── Deploying to ${NODE_NAME} (${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}}) ──"
echo ""

# ── Vendor dependencies ───────────────────────────────────────
echo "  [1/3] Vendoring dependencies..."
rm -rf vendor/
pip install --disable-pip-version-check -r requirements.txt --target=vendor/ --quiet
echo "        done."

# ── Sync to console ───────────────────────────────────────────
echo "  [2/3] Syncing files to ${REMOTE_PATH}..."
$SSH "rm -rf ${REMOTE_PATH}/* && mkdir -p ${REMOTE_PATH}/logs"

CONSOLE_EXCLUDES=()
for _d in batocera dc gba pluto ps3 wii ws; do
  [[ "$_d" != "$CONSOLE_DIR" ]] && CONSOLE_EXCLUDES+=("--exclude=$_d")
done

tar --no-xattrs \
    --exclude='.git' \
    --exclude='.idea' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='dev.py' \
    --exclude='deploy.sh' \
    "${CONSOLE_EXCLUDES[@]}" \
    -cf - . | $SSH "tar -xf - -C ${REMOTE_PATH}"

echo "        done."

# ── Install Linux-only dependencies on remote ─────────────────
echo "  [3/3] Installing Linux-only dependencies on ${NODE_NAME}..."
$SSH "pip3 install --disable-pip-version-check -r ${REMOTE_PATH}/requirements-linux.txt --target=${REMOTE_PATH}/vendor/ --quiet 2>/dev/null \
      || pip install --disable-pip-version-check -r ${REMOTE_PATH}/requirements-linux.txt --target=${REMOTE_PATH}/vendor/ --quiet" || true
echo "        done."

echo ""
echo "  ── Deploy complete — restart manually when ready ──"
echo ""