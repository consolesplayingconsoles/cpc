#!/usr/bin/env bash
#
# From-scratch DreamPi install for a Debian 13 (trixie) Raspberry Pi.
# Reproduces the /opt/dreampi + /etc setup by hand. There is NO SD image here on
# purpose: the official DreamPi image targets older Pis and does not boot clean
# on a Pi 5 / trixie, so we install the daemon manually.
#
# Run this ON the Pi (it needs sudo). Idempotent enough to re-run.
#
#   ./install.sh [DEST]     # DEST defaults to /opt/dreampi
#
set -euo pipefail

FORK="https://github.com/consolesplayingconsoles/dreampi.git"
DEST="${1:-/opt/dreampi}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "[dreampi] clone fork -> $DEST"
sudo mkdir -p "$DEST"
sudo chown "$USER:$USER" "$DEST"
[ -d "$DEST/.git" ] || git clone "$FORK" "$DEST"

echo "[dreampi] venv + Python deps"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --upgrade pip
"$DEST/venv/bin/pip" install -r "$HERE/requirements.txt"

echo "[dreampi] system packages (ppp + dnsmasq)"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ppp dnsmasq

echo "[dreampi] install config"
sudo install -m0644 "$HERE/etc/udev/99-dreampi-modem.rules"   /etc/udev/rules.d/99-dreampi-modem.rules
sudo install -m0644 "$HERE/etc/sysctl/99-dreampi-forward.conf" /etc/sysctl.d/99-dreampi-forward.conf
sudo install -m0644 "$HERE/etc/dnsmasq.conf"                   /etc/dnsmasq.conf
sudo install -m0644 "$HERE/etc/dreampi.service"               /etc/systemd/system/dreampi.service
# The unit hard-codes /opt/dreampi; rewrite it if you installed elsewhere.
if [ "$DEST" != "/opt/dreampi" ]; then
  sudo sed -i "s#/opt/dreampi#$DEST#g" /etc/systemd/system/dreampi.service
fi

echo "[dreampi] apply"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
sudo sysctl -p /etc/sysctl.d/99-dreampi-forward.conf
sudo systemctl enable dnsmasq  && sudo systemctl restart dnsmasq
sudo systemctl daemon-reload
sudo systemctl enable dreampi  && sudo systemctl restart dreampi

echo
echo "[dreampi] done. The modem (USB 0572:1340) must be present as /dev/dreampi-modem:"
ls -l /dev/dreampi-modem 2>/dev/null || echo "  (not found yet: plug the modem straight into the Pi, not a flaky hub)"
echo "[dreampi] watch it arm:  journalctl -t dreampi -f   (look for <LISTENING>)"
