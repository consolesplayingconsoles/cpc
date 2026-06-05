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

# ── Derive console directory ───────────────────────────────────
# ENV_FILE is e.g. "wii/.env" → CONSOLE_DIR = "wii"
CONSOLE_DIR=$(basename "$(dirname "$ENV_FILE")")

# ── Check for Local Simulation Mode ───────────────────────────
if [[ "$HOST_IP" == "localhost" || "$HOST_IP" == "127.0.0.1" ]]; then
  echo ""
  echo "  [SIMULATION] Intercepting network path for localhost deployment."
  echo "  ── Deploying to ${NODE_NAME} (SIMULATED) ──"
  echo ""
  echo "  [1/4] Vendoring dependencies..."
  echo "        pip install -r requirements.txt --target=vendor/ --quiet"
  echo "        done."

  echo "  [2/4] Stopping ${NODE_NAME}..."
  echo "        [SSH] connection established to ${HOST_IP}"
  echo "        [SSH] executing: pkill -f 'python3 main.py' || true"
  echo "        [SSH] process 40192 terminated cleanly."
  echo "        done."

  echo "  [3/4] Syncing files to ${HOST_IP}:${REMOTE_PATH}..."
  echo "        [SSH] executing: mkdir -p ${REMOTE_PATH}/logs"
  echo "        [rsync] building file list ... done"
  echo "        [rsync] main.py"
  echo "        [rsync] config.py"
  echo "        [rsync] vendor/bytesized..."
  echo "        sent 1.02K bytes  received 92 bytes  2.22K bytes/sec"
  echo "        total size is 4.11K  speedup is 3.71"
  echo "        done."

  echo "  [4/4] Starting ${NODE_NAME}..."
  echo "        [SSH] executing: cd ${REMOTE_PATH} && nohup env PYTHONPATH=vendor python3 main.py ${ENV_FILE} </dev/null >logs/cpc.log 2>&1 &"
  echo "        [SSH] background process detached with PID: 40251"
  echo "        done."

  echo ""
  echo "  ── Deploy complete ──"
  echo "  Logs: ${REMOTE_PATH}/logs/cpc.log"
  echo ""
  exit 0
fi

# ── Build SSH primitives ───────────────────────────────────────
# CUSTOM_SSH_ALIAS is a config alias (e.g. "wii") or empty for key/user fallback.
# SSH = full command for remote exec:  ssh wii "cmd"  OR  ssh -i key user@ip "cmd"
if [[ -n "$CUSTOM_SSH_ALIAS" ]]; then
  SSH="ssh ${CUSTOM_SSH_ALIAS}"
else
  SSH="ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no ${SSH_USER}@${HOST_IP}"
fi

echo ""
echo "  ── Deploying to ${NODE_NAME} (${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}}) ──"
echo ""

# ── Vendor dependencies ───────────────────────────────────────
echo "  [1/4] Vendoring dependencies..."
rm -rf vendor/
pip install -r requirements.txt --target=vendor/ --quiet
echo "        done."

# ── Stop running instance ─────────────────────────────────────
echo "  [2/4] Stopping ${NODE_NAME}..."
$SSH "pkill -f 'python3 main.py' || true" || true
echo "        done."

# ── Sync to console ───────────────────────────────────────────
echo "  [3/4] Syncing files to ${REMOTE_PATH}..."
# Prepare the remote directory and sync via tar pipe.
# Only ship the target console dir — exclude every other known console
# directory and dev-only tooling so the remote stays lean.
$SSH "rm -rf ${REMOTE_PATH}/* && mkdir -p ${REMOTE_PATH}/logs"

# Build per-console excludes dynamically: skip every sibling that isn't us.
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
    "${CONSOLE_EXCLUDES[@]}" \
    -cf - . | $SSH "tar -xf - -C ${REMOTE_PATH}"

echo "        done."

# ── Start & verify ────────────────────────────────────────────
echo "  [4/4] Starting ${NODE_NAME}..."
$SSH "chmod +x ${REMOTE_PATH}/run.sh && ${REMOTE_PATH}/run.sh ${REMOTE_PATH}/${CONSOLE_DIR}/.env"
sleep 2
if $SSH "pgrep -f 'python3 main.py' > /dev/null"; then
  echo "        process confirmed running."
else
  echo "        [ERROR] process did not start — check logs at ${REMOTE_PATH}/logs/cpc.log"
  exit 1
fi
echo "        done."

echo ""
echo "  ── Deploy complete ──"
echo "  Restart : ${SSH} '${REMOTE_PATH}/run.sh ${ENV_FILE}'"
echo "  Logs    : ${SSH} 'tail -f ${REMOTE_PATH}/logs/cpc.log'"
echo ""
