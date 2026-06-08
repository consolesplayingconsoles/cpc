#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — build locally and ship to a console node via SSH
#
#  Usage: ./deploy.sh <path-to-env-file>
#  Example: ./deploy.sh wii/.env
#
#  Lines starting with ##STEP:<name> are parsed by the Pluto API
#  to emit structured SSE step events. Keep them on their own line.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./deploy.sh <env-file>"
  exit 1
fi

ENV_FILE="$1"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] env file not found: $ENV_FILE"
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
  echo "[ERROR] Missing HOST_IP or NODE_NAME in $ENV_FILE"
  exit 1
fi

REMOTE_PATH="/opt/cpc"
CONSOLE_DIR=$(basename "$(dirname "$ENV_FILE")")

# ── Local simulation mode ─────────────────────────────────────
if [[ "$HOST_IP" == "localhost" || "$HOST_IP" == "127.0.0.1" ]]; then
  echo "[SIMULATION] ${NODE_NAME}"
  mkdir -p ${REMOTE_PATH}/logs
  echo "done."
  exit 0
fi

# ── SSH primitive ─────────────────────────────────────────────
if [[ -n "$CUSTOM_SSH_ALIAS" ]]; then
  SSH="ssh ${CUSTOM_SSH_ALIAS}"
else
  SSH="ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no ${SSH_USER}@${HOST_IP}"
fi

echo "deploying ${NODE_NAME} (${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}})"

# ── Step 1: vendor ────────────────────────────────────────────
echo "##STEP:vendor"
rm -rf vendor/
pip install --disable-pip-version-check -r requirements.txt --target=vendor/ --quiet
echo "vendor ok"

# ── Step 2: sync ──────────────────────────────────────────────
echo "##STEP:sync"
$SSH "rm -rf ${REMOTE_PATH}/* && mkdir -p ${REMOTE_PATH}/logs"

CONSOLE_EXCLUDES=()
for _d in batocera dc dreame gba pluto ps3 wii ws; do
  [[ "$_d" != "$CONSOLE_DIR" ]] && CONSOLE_EXCLUDES+=("--exclude=$_d")
done

tar --no-xattrs --no-fflags --no-mac-metadata \
    --exclude-from='.deployignore' \
    "${CONSOLE_EXCLUDES[@]}" \
    -cf - . | $SSH "tar -xf - -C ${REMOTE_PATH}"

echo "sync ok"

# ── Step 2b: peer env files ───────────────────────────────────
ENV_DEPS="$(_env_get DEPLOY_ENV_DEPS)"
if [[ -n "$ENV_DEPS" ]]; then
  for dep in $ENV_DEPS; do
    dep_env="${dep}/.env"
    if [[ -f "$dep_env" ]]; then
      $SSH "mkdir -p ${REMOTE_PATH}/${dep}"
      $SSH "cat > ${REMOTE_PATH}/${dep_env}" < "$dep_env"
      echo "env dep: ${dep_env}"
    else
      echo "[WARN] ${dep_env} not found, skipping"
    fi
  done
fi

# ── Step 3: linux deps ────────────────────────────────────────
if grep -qvE '^[[:space:]]*(#|$)' requirements-linux.txt; then
  echo "##STEP:deps"
  $SSH "pip3 install --disable-pip-version-check -r ${REMOTE_PATH}/requirements-linux.txt --target=${REMOTE_PATH}/vendor/ --quiet 2>/dev/null \
        || pip install --disable-pip-version-check -r ${REMOTE_PATH}/requirements-linux.txt --target=${REMOTE_PATH}/vendor/ --quiet" || true
  echo "deps ok"
fi

echo "##STEP:done"
echo "deploy complete — restart manually when ready"
