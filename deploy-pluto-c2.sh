#!/usr/bin/env bash
# -----------------------------------------------------------------
#  deploy-pluto-c2.sh -- the deploy ENGINE: build locally and ship ONE node over SSH.
#
#  Pluto owns deployment ("Pluto self-deploys everywhere"). You normally don't run
#  this by hand: the Pluto UI's DEPLOY button streams it per node -- the API shells
#  out to this script and parses the ##STEP:<name> lines into SSE progress events.
#  It is also the one-time DEV BOOTSTRAP: run it manually to stand the first node up.
#
#  WHAT each node gets is declarative, not hardcoded here: pluto/config/deploy.json
#  maps a node dir to a list of PAYLOADS, and this script knows HOW to ship each one.
#  Every node lands at the SAME remote root (/opt/cpc); multiple payloads coexist in
#  that one dir, told apart by name (e.g. the Pi gets the client + the hub backend).
#  Nodes not named in the map fall back to the "default" profile.
#
#  Payloads:
#    server  -- the Pluto dashboard (api + dist + config), run by serve.sh under systemd.
#    client  -- the python TUI client (pluto-python-tui + vendored deps).
#    (hub)    -- the Pi's native-protocol bridge backend.  [not built yet]
#
#  Usage: ./deploy-pluto-c2.sh <path-to-env-file>
#    ./deploy-pluto-c2.sh pluto/.env            # the Pluto host  -> server payload
#    ./deploy-pluto-c2.sh nodes/local/wii/.env  # a console node  -> client payload
# -----------------------------------------------------------------
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./deploy-pluto-c2.sh <env-file>"
  exit 1
fi

ENV_FILE="$1"
[[ -f "$ENV_FILE" ]] || { echo "[ERROR] env file not found: $ENV_FILE"; exit 1; }

REMOTE_ROOT="/opt/cpc"          # same path on every node
NODE_DIR=$(basename "$(dirname "$ENV_FILE")")
DEPLOY_MAP="pluto/config/deploy.json"

# -- parse env file -----------------------------------------------
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

# -- resolve payloads from the declarative map --------------------
[[ -f "$DEPLOY_MAP" ]] || { echo "[ERROR] deploy map not found: $DEPLOY_MAP"; exit 1; }
PAYLOADS="$(python3 - "$DEPLOY_MAP" "$NODE_DIR" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
node = sys.argv[2]
print(" ".join(m.get(node, m.get("default", []))))
PY
)"
[[ -n "$PAYLOADS" ]] || { echo "[ERROR] no deploy payloads for '$NODE_DIR' (and no default) in $DEPLOY_MAP"; exit 1; }

# -- local simulation mode ----------------------------------------
if [[ "$HOST_IP" == "localhost" || "$HOST_IP" == "127.0.0.1" ]]; then
  echo "[SIMULATION] ${NODE_NAME}: payloads [${PAYLOADS}] -> ${REMOTE_ROOT}"
  echo "done."
  exit 0
fi

# -- SSH primitive ------------------------------------------------
if [[ -n "$CUSTOM_SSH_ALIAS" ]]; then
  SSH="ssh ${CUSTOM_SSH_ALIAS}"
else
  SSH="ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no ${SSH_USER}@${HOST_IP}"
fi

echo "deploying ${NODE_NAME} (${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}}): payloads [${PAYLOADS}] -> ${REMOTE_ROOT}"

# =================================================================
#  Payload shippers. Each ships its files into ${REMOTE_ROOT} and writes the node
#  .env where that payload expects it -- BEFORE any restart, so a fail-fast service
#  never boots without config. The node root is wiped once (below) before all run.
# =================================================================

# server -- the Pluto dashboard. api.py reads ${REMOTE_ROOT}/.env; discovery reads
# the sibling /opt/nodes (base_dir/../nodes), so node identities ship there too.
payload_server() {
  echo "##STEP:build"
  npm --prefix pluto run build
  echo "build ok"

  echo "##STEP:sync"
  # Runnable surface only: pre-built SPA (dist/), stdlib API (api/), runtime config,
  # the starter, the systemd unit. --strip-components=1 drops the leading 'pluto/'.
  tar --no-xattrs --no-fflags --no-mac-metadata \
      -cf - pluto/api pluto/dist pluto/config pluto/serve.sh pluto/deploy/pluto.service \
      | $SSH "tar -xf - --strip-components=1 -C ${REMOTE_ROOT}"
  $SSH "cat > ${REMOTE_ROOT}/.env" < "$ENV_FILE"
  $SSH "chmod +x ${REMOTE_ROOT}/serve.sh"

  # Cloud connectors are discovered nodes: ship identity-only .env.sample (no
  # secrets) to /opt/nodes/cloud/. --strip-components=1 drops the leading 'nodes/'.
  $SSH "rm -rf /opt/nodes/cloud && mkdir -p /opt/nodes/cloud"
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - nodes/cloud/*/.env.sample \
      | $SSH "tar -xf - --strip-components=1 -C /opt/nodes"

  # Local LAN nodes: the server pings them, so it needs identity + IP, but it never
  # deploys (that's the Lab), so ship a SANITISED .env -- identity/IP/display only,
  # SSH + deploy creds + workspace path stripped. Placeholders ship their .sample.
  $SSH "rm -rf /opt/nodes/local && mkdir -p /opt/nodes/local"
  if ls nodes/local/*/.env.sample >/dev/null 2>&1; then
    tar --no-xattrs --no-fflags --no-mac-metadata -cf - nodes/local/*/.env.sample \
        | $SSH "tar -xf - --strip-components=1 -C /opt/nodes"
  fi
  for envf in nodes/local/*/.env; do
    [ -f "$envf" ] || continue
    name=$(basename "$(dirname "$envf")")
    grep -E '^(NODE_NAME|HOST_IP|UI_PRIMARY_COLOR|UI_SECONDARY_COLOR|SMB_PATH|OS)=' "$envf" \
        | $SSH "mkdir -p /opt/nodes/local/${name} && cat > /opt/nodes/local/${name}/.env"
  done
  echo "sync ok"

  # Restart. Re-sync the unit so a first install (or the /opt/pluto -> /opt/cpc path
  # move) takes effect; ExecStart points at ${REMOTE_ROOT}/serve.sh.
  echo "##STEP:restart"
  if $SSH "[ -d /run/systemd/system ]"; then
    if $SSH "cp ${REMOTE_ROOT}/deploy/pluto.service /etc/systemd/system/pluto.service && systemctl daemon-reload && systemctl enable pluto >/dev/null 2>&1 && systemctl restart pluto"; then
      echo "restarted via systemd (pluto.service synced to ${REMOTE_ROOT})"
    else
      echo "[note] could not sync/restart the unit (needs root). Re-point it once:"
      echo "  ssh ${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}} 'sudo cp ${REMOTE_ROOT}/deploy/pluto.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now pluto'"
    fi
  else
    echo "not managed by systemd -- run ${REMOTE_ROOT}/serve.sh manually"
  fi
}

# client -- the monolithic python TUI. Ships the same everywhere; lands at
# ${REMOTE_ROOT}/pluto-python-tui and reads ../${NODE_DIR}/.env (run.sh auto-detect).
payload_client() {
  echo "##STEP:vendor"
  rm -rf pluto-python-tui/vendor/
  pip install --disable-pip-version-check -r pluto-python-tui/requirements.txt --target=pluto-python-tui/vendor/ --quiet
  echo "vendor ok"

  echo "##STEP:sync"
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - pluto-python-tui \
      | $SSH "tar -xf - -C ${REMOTE_ROOT}"
  # This node's .env one level up from the client dir, keyed by node dir name, so
  # run.sh / sibling_env resolve ../${NODE_DIR}/.env.
  $SSH "mkdir -p ${REMOTE_ROOT}/${NODE_DIR} && cat > ${REMOTE_ROOT}/${NODE_DIR}/.env" < "$ENV_FILE"
  echo "sync ok"

  if grep -qvE '^[[:space:]]*(#|$)' pluto-python-tui/requirements-linux.txt; then
    echo "##STEP:deps"
    RL="${REMOTE_ROOT}/pluto-python-tui/requirements-linux.txt"
    RV="${REMOTE_ROOT}/pluto-python-tui/vendor/"
    $SSH "pip3 install --disable-pip-version-check -r ${RL} --target=${RV} --quiet 2>/dev/null \
          || pip install --disable-pip-version-check -r ${RL} --target=${RV} --quiet" || true
    echo "deps ok"
  fi
}

# hub -- the Pi's native-protocol bridge backend (scaffold). Lands at
# ${REMOTE_ROOT}/pluto-pi-hub and reads the shared ${NODE_DIR} .env that the client
# payload writes (the Pi always deploys client + hub together, so no env write here).
payload_hub() {
  echo "##STEP:sync"
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - pluto-pi-hub \
      | $SSH "tar -xf - -C ${REMOTE_ROOT}"
  $SSH "chmod +x ${REMOTE_ROOT}/pluto-pi-hub/run.sh ${REMOTE_ROOT}/pluto-pi-hub/hub.py"
  echo "sync ok"

  # The engine stays BLIND to firmware: it just hands off to the hub's own
  # propagate, which flashes each attached Pico with its role's firmware per the
  # .env binding (PICO_<chipid>=<role>). The "next layer" is the hub's job.
  # Pure stdlib (raw-REPL flasher), so plain python3 -- no mpremote dependency.
  echo "##STEP:propagate"
  $SSH "python3 ${REMOTE_ROOT}/pluto-pi-hub/propagate.py ${REMOTE_ROOT}/${NODE_DIR}/.env" || true
}

# =================================================================
#  Ship: wipe the node root's CONTENTS once (not the dir itself), then run each
#  payload into it. We delete contents rather than the dir so a NON-root deploy
#  user works too: it owns /opt/cpc's contents but can't recreate /opt/cpc under
#  root-owned /opt. One-time per non-root node:
#    sudo mkdir -p /opt/cpc && sudo chown <deploy-user> /opt/cpc
# =================================================================
$SSH "find ${REMOTE_ROOT} -mindepth 1 -delete 2>/dev/null; mkdir -p ${REMOTE_ROOT}/logs"

for payload in $PAYLOADS; do
  if ! declare -F "payload_${payload}" >/dev/null; then
    echo "[ERROR] unknown payload '${payload}' for node '${NODE_DIR}' -- no payload_${payload}()"
    exit 1
  fi
  "payload_${payload}"
done

echo "##STEP:done"
if echo " ${PAYLOADS} " | grep -q " server "; then
  echo "deploy complete -- http://${HOST_IP}:5173  (API :7700)"
else
  echo "deploy complete -- ${NODE_NAME} [${PAYLOADS}] at ${REMOTE_ROOT}"
fi
