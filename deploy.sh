#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — build locally and ship to a console node via SSH
#
#  Usage: ./deploy.sh <path-to-env-file>
#  Examples:
#    ./deploy.sh wii/.env          # console node
#    ./deploy.sh pluto/.env        # Pluto host (ships api/ + dist/)
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

# ── Pluto host deploy ─────────────────────────────────────────
# Pluto is pure-stdlib Python (api/) + a pre-built static SPA (dist/). The API
# reads its config/ JSON (connections.json, chat.json) at runtime, so ship that
# dir too. No vendoring, no pip — the box only needs python3 to serve.
if [[ "$CONSOLE_DIR" == "pluto" ]]; then
  REMOTE_PLUTO="/opt/pluto"

  echo "##STEP:build"
  npm --prefix pluto run build
  echo "build ok"

  echo "##STEP:sync"
  $SSH "rm -rf ${REMOTE_PLUTO} && mkdir -p ${REMOTE_PLUTO}"
  # Ship the runnable surface only — the pre-built SPA (dist/), the stdlib API
  # (api/), the runtime data, the starter, and the systemd unit. No src/, no
  # node_modules. --strip-components=1 drops the leading 'pluto/'.
  tar --no-xattrs --no-fflags --no-mac-metadata \
      -cf - pluto/api pluto/dist pluto/config pluto/serve.sh pluto/deploy/pluto.service \
      | $SSH "tar -xf - --strip-components=1 -C ${REMOTE_PLUTO}"
  # config/ carries the runtime JSON the API reads (connections.json, chat.json);
  # layout.json rides along too (frontend-only, already bundled in dist — harmless).
  $SSH "cat > ${REMOTE_PLUTO}/.env"      < "$ENV_FILE"
  $SSH "chmod +x ${REMOTE_PLUTO}/serve.sh"
  # Mappings are CONFIG/DATA that PLUTO reads to translate vacuum events -> ops and
  # hand them to the Pi. They ship WITH Pluto (single source of truth) and live at
  # /opt/pluto/mappings (serve.sh points CPC_MAPPINGS there). Deliberately NOT in
  # the cpc-python-client console deploy -- shipping them to the Pi too would drift.
  # (No --strip-components: keep the mappings/ dir intact.)
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - mappings \
      | $SSH "tar -xf - -C ${REMOTE_PLUTO}"
  echo "sync ok"

  # Restart so the new code takes effect. If pluto.service is installed under a
  # live systemd, restart it (zero-touch); otherwise leave a one-time hint.
  echo "##STEP:restart"
  if $SSH "[ -d /run/systemd/system ] && systemctl cat pluto.service >/dev/null 2>&1"; then
    $SSH "systemctl restart pluto" && echo "restarted via systemd (pluto.service)"
  else
    echo "not managed by systemd — restart manually:  /opt/pluto/serve.sh"
    echo "  one-time setup (Debian w/ systemd):"
    echo "    ssh ${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}} 'cp /opt/pluto/deploy/pluto.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now pluto'"
  fi

  echo "##STEP:done"
  echo "deploy complete — http://${HOST_IP}:5173  (API :7700)"
  exit 0
fi

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
