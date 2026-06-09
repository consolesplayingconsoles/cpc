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
rm -rf cpc-python-client/vendor/
pip install --disable-pip-version-check -r cpc-python-client/requirements.txt --target=cpc-python-client/vendor/ --quiet
echo "vendor ok"

# ── Step 2: sync ──────────────────────────────────────────────
echo "##STEP:sync"
$SSH "rm -rf ${REMOTE_PATH}/* && mkdir -p ${REMOTE_PATH}/logs"

# Allowlist: ship ONLY the python client dir (code + vendored deps). No
# .deployignore to babysit — anything else at the repo root (pluto/, birdbuddy/,
# scripts/, start-pluto.sh, *.md, other consoles, ...) can't leak; it's not listed.
INCLUDE=( cpc-python-client )

tar --no-xattrs --no-fflags --no-mac-metadata \
    -cf - "${INCLUDE[@]}" | $SSH "tar -xf - -C ${REMOTE_PATH}"

# This console's own .env, streamed separately so an absolute ENV_FILE path
# (as the Pluto API passes) lands at the right relative spot, not /Users/...
$SSH "mkdir -p ${REMOTE_PATH}/${CONSOLE_DIR}"
$SSH "cat > ${REMOTE_PATH}/${CONSOLE_DIR}/.env" < "$ENV_FILE"

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
if grep -qvE '^[[:space:]]*(#|$)' cpc-python-client/requirements-linux.txt; then
  echo "##STEP:deps"
  RL="${REMOTE_PATH}/cpc-python-client/requirements-linux.txt"
  RV="${REMOTE_PATH}/cpc-python-client/vendor/"
  $SSH "pip3 install --disable-pip-version-check -r ${RL} --target=${RV} --quiet 2>/dev/null \
        || pip install --disable-pip-version-check -r ${RL} --target=${RV} --quiet" || true
  echo "deps ok"
fi

echo "##STEP:done"
echo "deploy complete — restart manually when ready"
