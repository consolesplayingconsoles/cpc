#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — build locally and ship to a console node via SSH
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
  grep -E "^$1=" "$ENV_FILE" | cut -d= -f2- | tr -d '[:space:]'
}

HOST_IP="$(_env_get HOST_IP)"
SSH_USER="$(_env_get SSH_USER)"
SSH_KEY_PATH="$(_env_get SSH_KEY_PATH)"
NODE_NAME="$(_env_get NODE_NAME)"

if [[ -z "$HOST_IP" || -z "$SSH_USER" || -z "$SSH_KEY_PATH" || -z "$NODE_NAME" ]]; then
  echo ""
  echo "  [ERROR] Missing required fields in $ENV_FILE"
  echo ""
  exit 1
fi

REMOTE_PATH="/opt/cpc"
SSH_OPTS="-i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no"
SSH="ssh $SSH_OPTS ${SSH_USER}@${HOST_IP}"

echo ""
echo "  ── Deploying to ${NODE_NAME} (${SSH_USER}@${HOST_IP}) ──"
echo ""

# ── Vendor dependencies ───────────────────────────────────────
echo "  [1/4] Vendoring dependencies..."
rm -rf vendor/
pip install -r requirements.txt --target=vendor/ --quiet
echo "        done."

# ── Stop running instance ─────────────────────────────────────
echo "  [2/4] Stopping ${NODE_NAME}..."
$SSH "pkill -f 'python3 main.py' || true"
echo "        done."

# ── Sync to console ───────────────────────────────────────────
echo "  [3/4] Syncing files to ${HOST_IP}:${REMOTE_PATH}..."
$SSH "mkdir -p ${REMOTE_PATH}/logs"
rsync -az --delete \
  --exclude='.git' \
  --exclude='.idea' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -e "ssh $SSH_OPTS" \
  ./ "${SSH_USER}@${HOST_IP}:${REMOTE_PATH}/"
echo "        done."

# ── Start ─────────────────────────────────────────────────────
echo "  [4/4] Starting ${NODE_NAME}..."
$SSH "cd ${REMOTE_PATH} && nohup env PYTHONPATH=vendor python3 main.py ${ENV_FILE} </dev/null >logs/cpc.log 2>&1 &"
echo "        done."

echo ""
echo "  ── Deploy complete ──"
echo "  Logs: ${REMOTE_PATH}/logs/cpc.log"
echo ""
