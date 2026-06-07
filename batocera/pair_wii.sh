#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  pair_wii.sh — Bluetooth setup helper for the Wii bridge
#
#  Checks adapter state, reads BT_MAC from ../wii/.env, and
#  optionally scans for the Wii if the MAC is not set yet.
#
#  Usage: ./pair_wii.sh [wii-bt-mac]
#  The MAC argument overrides wii/.env BT_MAC for this session only.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WII_ENV="${SCRIPT_DIR}/../wii/.env"

# ── Parse wii env ─────────────────────────────────────────────
_env_get() {
  local key="$1" val=""
  [[ ! -f "$WII_ENV" ]] && echo "" && return
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in
      "${key}="*)
        val="${line#*=}"
        val="${val#\"}" ; val="${val%\"}"
        val="${val#\'}" ; val="${val%\'}"
        break ;;
    esac
  done < "$WII_ENV"
  echo "$val"
}

WII_MAC="${1:-$(_env_get BT_MAC)}"

echo ""
echo "  ── CPC / Wii BT Pairing Helper ──"
echo ""

# ── Check Bluetooth adapter ───────────────────────────────────
if ! command -v bluetoothctl &>/dev/null; then
  echo "  [ERROR] bluetoothctl not found — is bluez installed?"
  echo ""
  exit 1
fi

BT_STATE=$(bluetoothctl show 2>/dev/null | grep -i "powered" | awk '{print $2}' || true)
if [[ "$BT_STATE" != "yes" ]]; then
  echo "  [WARN] Bluetooth adapter is off or not found. Powering on..."
  bluetoothctl power on
  sleep 1
fi
echo "  [OK] Bluetooth adapter is up."
echo ""

# ── MAC resolution ────────────────────────────────────────────
if [[ -z "$WII_MAC" ]]; then
  echo "  [INFO] BT_MAC not set in wii/.env."
  echo "  Starting a 10-second scan — power on your Wii now,"
  echo "  then press SYNC on the back to make it discoverable."
  echo ""
  bluetoothctl --timeout 10 scan on 2>/dev/null || true
  echo ""
  echo "  Devices found:"
  bluetoothctl devices 2>/dev/null | grep -v "^$" || echo "  (none)"
  echo ""
  echo "  Copy the Wii's MAC address above and set BT_MAC= in wii/.env,"
  echo "  then re-run this script."
  echo ""
  exit 0
fi

echo "  Wii MAC : ${WII_MAC}"
echo ""

# ── Test L2CAP reachability ───────────────────────────────────
echo "  Testing L2CAP ping (3 packets)..."
if command -v l2ping &>/dev/null; then
  if l2ping -c 3 "$WII_MAC" &>/dev/null; then
    echo "  [OK] Wii is reachable."
  else
    echo "  [WARN] l2ping failed. Wii may be off or not in range."
  fi
else
  echo "  [INFO] l2ping not available — skipping reachability check."
fi
echo ""

# ── Notes on HID emulation ────────────────────────────────────
echo "  NOTE: dreame_to_wii_bridge.py sends raw L2CAP HID reports to the"
echo "  Wii's interrupt channel (PSM 0x13). For the Wii to accept them,"
echo "  batocera must be paired as a Bluetooth HID device from the Wii's"
echo "  perspective. Steps:"
echo ""
echo "    1. On the Wii: Settings -> Wii Remotes -> Reconnect"
echo "       (this opens the HID host accept window)"
echo "    2. On batocera: bluetoothctl pair ${WII_MAC}"
echo "                    bluetoothctl trust ${WII_MAC}"
echo "    3. Run: python3 batocera/dreame_to_wii_bridge.py"
echo ""
