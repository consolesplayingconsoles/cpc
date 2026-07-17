#!/usr/bin/env bash
# -----------------------------------------------------------------
#  deploy.sh -- the deploy ENGINE: build locally and ship ONE node over SSH.
#
#  Pluto owns deployment ("Pluto self-deploys everywhere"). You normally don't run
#  this by hand: the Pluto UI's DEPLOY button streams it per node -- the API shells
#  out to this script and parses the ##STEP:<name> lines into SSE progress events.
#  It is also the one-time DEV BOOTSTRAP: run it manually to stand the first node up.
#
#  WHAT each node gets is declarative, not hardcoded here: pluto/config/payloads.json
#  maps a node dir to a list of PAYLOADS, and this script knows HOW to ship each one.
#  Every node lands at the SAME remote root (/opt/cpc); multiple payloads coexist in
#  that one dir, told apart by name (e.g. the Pi gets the client + the hub backend).
#  Nodes not named in the map fall back to the "default" profile.
#
#  Payloads:
#    server    -- the Pluto dashboard (api + dist + config), run by serve.sh under systemd.
#    client    -- the python TUI client (pluto-python-tui + vendored deps).
#    hub       -- the Pi's bridge backend; its always-up op receiver runs under systemd.
#    translate -- the Dreamcast translation API on Batocera, under batocera-services.
#
#  Usage: ./deploy.sh <path-to-env-file>
#    ./deploy.sh pluto/.env            # the Pluto host  -> server payload
#    ./deploy.sh nodes/local/wii/.env  # a console node  -> client payload
# -----------------------------------------------------------------
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./deploy.sh <env-file>"
  exit 1
fi

ENV_FILE="$1"
[[ -f "$ENV_FILE" ]] || { echo "[ERROR] env file not found: $ENV_FILE"; exit 1; }

REMOTE_ROOT="/opt/cpc"          # same path on every node
NODE_DIR=$(basename "$(dirname "$ENV_FILE")")
DEPLOY_MAP="pluto/config/payloads.json"

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

# -- local vs remote payloads -------------------------------------
# Some payloads flash the device LOCALLY (over USB via mpremote) -- no SSH, no remote
# root. If EVERY payload is local, skip all the remote plumbing (SSH primitive + the
# node-root wipe) so a creds-less device (a Pico) doesn't try to build a broken ssh cmd.
LOCAL_PAYLOADS=" pico "
NEEDS_REMOTE=0
for p in $PAYLOADS; do
  case "$LOCAL_PAYLOADS" in *" $p "*) : ;; *) NEEDS_REMOTE=1 ;; esac
done

if [[ $NEEDS_REMOTE -eq 1 ]]; then
  # -- SSH primitive ----------------------------------------------
  if [[ -n "$CUSTOM_SSH_ALIAS" ]]; then
    SSH="ssh ${CUSTOM_SSH_ALIAS}"
  else
    SSH="ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no ${SSH_USER}@${HOST_IP}"
  fi

  # Privilege prefix, evaluated ON THE REMOTE at run time: empty when the deploy user
  # is already root, else `sudo -n`. Some nodes deploy as a passwordless-sudo user;
  # others log in as root, where sudo may not even be installed -- calling `sudo` there
  # fails and the service never starts. So escalate only when we actually need to.
  # Single-quoted here so $(id -u)/$SUDO stay literal and resolve on the node, not locally.
  PRIV='if [ "$(id -u)" -eq 0 ]; then SUDO=; else SUDO="sudo -n"; fi;'

  echo "deploying ${NODE_NAME} (${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}}): payloads [${PAYLOADS}] -> ${REMOTE_ROOT}"
else
  echo "deploying ${NODE_NAME}: payloads [${PAYLOADS}] (local flash -- no remote)"
fi

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

  # Local LAN nodes: the server pings them AND drives them (C2 dials each node's op
  # receiver), so it needs identity + IP + bridge port -- but it never DEPLOYS (that's
  # the Lab), so ship a SANITISED .env: identity/IP/display + the non-secret bridge
  # port, with SSH + deploy creds + workspace path stripped. Placeholders ship .sample.
  $SSH "rm -rf /opt/nodes/local && mkdir -p /opt/nodes/local"
  if ls nodes/local/*/.env.sample >/dev/null 2>&1; then
    tar --no-xattrs --no-fflags --no-mac-metadata -cf - nodes/local/*/.env.sample \
        | $SSH "tar -xf - --strip-components=1 -C /opt/nodes"
  fi
  for envf in nodes/local/*/.env; do
    [ -f "$envf" ] || continue
    name=$(basename "$(dirname "$envf")")
    grep -E '^(NODE_NAME|HOST_IP|PI_BRIDGE_PORT|UI_PRIMARY_COLOR|UI_SECONDARY_COLOR|SMB_PATH|OS)=' "$envf" \
        | $SSH "mkdir -p /opt/nodes/local/${name} && cat > /opt/nodes/local/${name}/.env"
  done

  # OpenAPI specs for /docs (the API serves them same-origin). Ship the non-Pluto
  # ones into a flat specs/ dir the API resolves; Pluto's own rides inside api/.
  $SSH "mkdir -p ${REMOTE_ROOT}/specs"
  $SSH "cat > ${REMOTE_ROOT}/specs/pluto.yaml"     < pluto/api/openapi.yaml
  $SSH "cat > ${REMOTE_ROOT}/specs/translate.yaml" < pluto-translate/openapi.yaml
  $SSH "cat > ${REMOTE_ROOT}/specs/pico-hub.yaml"    < pluto-pico-hub/openapi.yaml
  $SSH "cat > ${REMOTE_ROOT}/specs/drive.yaml"       < pluto-drive/openapi.yaml
  $SSH "cat > ${REMOTE_ROOT}/specs/roomba-rally.yaml"    < nodes/local/roomba-rally/openapi.yaml
  $SSH "cat > ${REMOTE_ROOT}/specs/crazy-roomba.yaml"    < nodes/local/crazy-roomba/openapi.yaml
  echo "sync ok"

  # Restart. Re-sync the unit so a first install (or the /opt/pluto -> /opt/cpc path
  # move) takes effect; ExecStart points at ${REMOTE_ROOT}/serve.sh.
  echo "##STEP:restart"
  if $SSH "[ -d /run/systemd/system ]"; then
    if $SSH "$PRIV \$SUDO cp ${REMOTE_ROOT}/deploy/pluto.service /etc/systemd/system/pluto.service && \$SUDO systemctl daemon-reload && \$SUDO systemctl enable pluto >/dev/null 2>&1 && \$SUDO systemctl restart pluto"; then
      echo "restarted via systemd (pluto.service synced to ${REMOTE_ROOT})"
    else
      echo "[ERROR] could not sync/restart the unit -- the service is NOT running. Re-point it once (needs root):"
      echo "  ssh ${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}} 'sudo cp ${REMOTE_ROOT}/deploy/pluto.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now pluto'"
      exit 1
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
# ${REMOTE_ROOT}/pluto-pico-hub and reads the shared ${NODE_DIR} .env that the client
# payload writes (the Pi always deploys client + hub together, so no env write here).
payload_hub() {
  echo "##STEP:sync"
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - pluto-pico-hub \
      | $SSH "tar -xf - -C ${REMOTE_ROOT}"
  $SSH "chmod +x ${REMOTE_ROOT}/pluto-pico-hub/run.sh ${REMOTE_ROOT}/pluto-pico-hub/hub.py"
  echo "sync ok"

  # The engine stays BLIND to firmware: it just hands off to the hub's own
  # propagate, which flashes each attached Pico with its role's firmware per the
  # .env binding (PICO_<chipid>=<role>). The "next layer" is the hub's job.
  # Pure stdlib (raw-REPL flasher), so plain python3 -- no mpremote dependency.
  echo "##STEP:propagate"
  $SSH "python3 ${REMOTE_ROOT}/pluto-pico-hub/propagate.py ${REMOTE_ROOT}/${NODE_DIR}/.env" || true

  # Bring up the always-up op receiver (Pluto's op stream -> Pico). Same systemd
  # pattern as the server: sync the unit, then `restart` -- which STOPS the instance
  # currently holding the UART + listen port (graceful SIGTERM) before the fresh one
  # binds them, so a redeploy hands off cleanly.
  echo "##STEP:restart"
  HUB_UNIT="${REMOTE_ROOT}/pluto-pico-hub/deploy/cpc-hub.service"
  if $SSH "[ -d /run/systemd/system ]"; then
    if $SSH "$PRIV \$SUDO cp ${HUB_UNIT} /etc/systemd/system/cpc-hub.service && \$SUDO systemctl daemon-reload && \$SUDO systemctl enable cpc-hub >/dev/null 2>&1 && \$SUDO systemctl restart cpc-hub"; then
      echo "restarted via systemd (cpc-hub.service synced to ${REMOTE_ROOT})"
    else
      echo "[ERROR] could not sync/restart the unit -- the op receiver is NOT running. Re-point it once (needs root):"
      echo "  ssh ${CUSTOM_SSH_ALIAS:-${SSH_USER}@${HOST_IP}} 'sudo cp ${HUB_UNIT} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now cpc-hub'"
      exit 1
    fi
  else
    echo "not managed by systemd -- run ${REMOTE_ROOT}/pluto-pico-hub/run.sh serve manually"
  fi
}

# drive -- the standalone drive API (pluto-drive). On the C2 the pluto server payload
# (api.py) launches it as a child, so this payload only ships the package; the server
# restart brings it up. (On the Pi it runs under its own systemd -- see step 4.) Ship
# to ${REMOTE_ROOT}/pluto-drive so api.py finds it beside the flattened pluto contents.
payload_drive() {
  echo "##STEP:sync"
  tar --no-xattrs --no-fflags --no-mac-metadata -cf - pluto-drive \
      | $SSH "tar -xf - -C ${REMOTE_ROOT}"
  $SSH "chmod +x ${REMOTE_ROOT}/pluto-drive/run.sh"
  # The drive engine needs the mapping store. The pluto (C2) node's server payload
  # already ships config/; elsewhere (the Pi) ship mappings so run.sh finds them at
  # ${REMOTE_ROOT}/pluto/config/mappings.
  case " $PAYLOADS " in
    *" server "*) : ;;
    *)
      $SSH "mkdir -p ${REMOTE_ROOT}/pluto/config"
      tar --no-xattrs --no-fflags --no-mac-metadata -cf - pluto/config/mappings \
          | $SSH "tar -xf - --strip-components=1 -C ${REMOTE_ROOT}/pluto"
      ;;
  esac
  echo "sync ok"

  # On a node WITHOUT the pluto server (the Pi), nothing else launches the drive, so it
  # runs under its OWN systemd. On the C2 the server payload's api.py spawns it -> skip.
  case " $PAYLOADS " in
    *" server "*) echo "  drive: launched by the pluto api (no systemd here)" ;;
    *)
      echo "##STEP:restart"
      if $SSH "[ -d /run/systemd/system ]"; then
        DRIVE_UNIT="${REMOTE_ROOT}/pluto-drive/deploy/cpc-drive.service"
        if $SSH "$PRIV \$SUDO cp ${DRIVE_UNIT} /etc/systemd/system/cpc-drive.service && \$SUDO systemctl daemon-reload && \$SUDO systemctl enable cpc-drive >/dev/null 2>&1 && \$SUDO systemctl restart cpc-drive"; then
          echo "cpc-drive.service restarted"
        else
          echo "[WARN] cpc-drive.service install/restart failed"
        fi
      else
        echo "no systemd -- run ${REMOTE_ROOT}/pluto-drive/run.sh manually"
      fi
      ;;
  esac
}

# translate -- the Dreamcast translation API (pluto-translate). Unlike server/hub
# its node is Batocera, which has NO systemd (uses batocera-services) and an
# EPHEMERAL overlay / (only /userdata persists). So it lands in /userdata and
# installs a batocera-service; falls back to a plain run.sh launch otherwise.
payload_translate() {
  TR_DIR=/userdata/cpc-scripts          # persistent on Batocera (/ is an overlay)
  echo "##STEP:sync"
  $SSH "rm -rf ${TR_DIR}; mkdir -p ${TR_DIR}"
  tar --no-xattrs --no-fflags --no-mac-metadata -C pluto-translate \
      --exclude='__pycache__' --exclude='deploy' --exclude='docs' -cf - . \
      | $SSH "tar -xf - -C ${TR_DIR}"
  $SSH "chmod +x ${TR_DIR}/run.sh ${TR_DIR}/*.sh ${TR_DIR}/dc/*.sh"

  # Dreamcast tools reference docs: deployed to /userdata/share/ (actual tools must be
  # installed separately on Batocera and available in PATH as a prerequisite).
  $SSH "mkdir -p /userdata/share/dreamcast"
  tar --no-xattrs --no-fflags --no-mac-metadata -C nodes/local/batocera/share \
      -cf - . | $SSH "tar -xf - -C /userdata/share"
  echo "sync ok"

  echo "##STEP:restart"
  if $SSH "command -v batocera-services >/dev/null 2>&1"; then
    $SSH "mkdir -p /userdata/system/services && cat > /userdata/system/services/cpc-translate && chmod +x /userdata/system/services/cpc-translate" < pluto-translate/deploy/cpc-translate
    # stop kills by port (an old orphan too), then enable (boot) + start.
    $SSH "batocera-services stop cpc-translate >/dev/null 2>&1; batocera-services enable cpc-translate >/dev/null 2>&1; batocera-services start cpc-translate"
    echo "restarted via batocera-services (cpc-translate)"
  else
    $SSH "F=\$(fuser 7711/tcp 2>/dev/null); [ -n \"\$F\" ] && kill \$F 2>/dev/null; sleep 1; setsid sh ${TR_DIR}/run.sh serve > ${TR_DIR}/service.log 2>&1 < /dev/null &"
    echo "started via run.sh (no batocera-services)"
  fi
}

payload_pico() {
  # Roomba Pico flash: substitute secrets from .env into template, then flash via mpremote.
  echo "##STEP:pico-flash"
  NODE_SCRIPT="nodes/local/${NODE_DIR}/scripts/main.py"
  [[ -f "$NODE_SCRIPT" ]] || { echo "[ERROR] no script at $NODE_SCRIPT"; exit 1; }

  # Extract config from .env (roomba-rally-specific keys; generalize if adding other Pico nodes)
  SSID="$(_env_get ROOMBA_SSID)"
  PASS="$(_env_get ROOMBA_PASSWORD)"
  PORT="$(_env_get HOST_PORT)"
  [[ -n "$SSID" && -n "$PASS" && -n "$PORT" ]] || { echo "[ERROR] ROOMBA_SSID, ROOMBA_PASSWORD, or HOST_PORT missing"; exit 1; }

  TMPFILE=$(mktemp)
  sed "s|@@ROOMBA_SSID@@|${SSID}|g; s|@@ROOMBA_PASSWORD@@|${PASS}|g; s|@@HOST_PORT@@|${PORT}|g" \
      "$NODE_SCRIPT" > "$TMPFILE"

  # Flash via mpremote (Pico must be plugged in + in bootloader or running MicroPython)
  if ! command -v mpremote &>/dev/null; then
    echo "[ERROR] mpremote not found. Install: pip install mpremote"
    rm "$TMPFILE"
    exit 1
  fi

  # Flash, then reset. Check the copy explicitly: in `cp && reset` under `set -e`, a
  # failing `cp` is EXEMPT (it's not the final command of the && list), so the script
  # would sail past to "[done]" even when no board was found. Gate on cp's real result.
  if ! mpremote cp "$TMPFILE" ":main.py"; then
    rm -f "$TMPFILE"
    echo "[ERROR] flash failed -- no Pico found on USB (attached? not held open by Thonny/another serial app?)"
    exit 1
  fi
  mpremote reset || echo "[warn] reset didn't confirm -- power-cycle the board if it didn't restart"
  echo "[done] Pico flashed and reset"
  rm -f "$TMPFILE"
}

# =================================================================
#  Ship: wipe the node root's CONTENTS once (not the dir itself), then run each
#  payload into it. We delete contents rather than the dir so a NON-root deploy
#  user works too: it owns /opt/cpc's contents but can't recreate /opt/cpc under
#  root-owned /opt. One-time per non-root node:
#    sudo mkdir -p /opt/cpc && sudo chown <deploy-user> /opt/cpc
# =================================================================
if [[ $NEEDS_REMOTE -eq 1 ]]; then
  $SSH "find ${REMOTE_ROOT} -mindepth 1 -delete 2>/dev/null; mkdir -p ${REMOTE_ROOT}/logs"
fi

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
elif [[ $NEEDS_REMOTE -eq 1 ]]; then
  echo "deploy complete -- ${NODE_NAME} [${PAYLOADS}] at ${REMOTE_ROOT}"
else
  echo "deploy complete -- ${NODE_NAME} [${PAYLOADS}]"
fi
