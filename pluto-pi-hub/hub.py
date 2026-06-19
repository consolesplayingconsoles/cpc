#!/usr/bin/env python3
"""
hub.py -- CPC Pi-Hub entrypoint (SCAFFOLD).

The Pi-Hub is NOT a Pluto instance and NOT a webserver. It is a small set of
purpose-built, single-purpose BRIDGE processes that let consoles which never
spoke TCP/IP reach the network: HID over UART to a Pico, per-console serial
transports, DreamPi for the Dreamcast. The Lab/C2 Pluto instances manage these
bridges remotely as a C2 feature; this process is the thing they manage, not a
peer instance of Pluto.

Scaffold status: this proves the deploy path (it ships as the `hub` payload to
/opt/cpc/pluto-pi-hub and reads the shared ../<node>/.env written by the client
payload) and gives the bridges a home under bridges/. No bridge is active yet.
Pure stdlib, 3.6-safe, ASCII output only.
"""
import os
import sys


def load_env(path):
    """Minimal .env parser (stdlib, 3.6). Same shape as the client's env.load_env."""
    cfg = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


# Bridges are built from the node .env -- config decides which exist. Each exposes
# start()/stop()/status(); the Phase-2 supervisor wires an op source into them.
def build_bridges(cfg):
    """Instantiate the bridges this node's .env configures."""
    bridges = []
    if cfg.get("UART_DEVICE"):                 # controller bridge: ops -> GP2040 frames -> Pico
        from bridges.hid import HidBridge
        bridges.append(HidBridge(cfg))
    return bridges


def main(argv):
    env_path = argv[1] if len(argv) > 1 else ""
    cfg = load_env(env_path)
    name = cfg.get("NODE_NAME", "Pi-Hub")
    bridges = build_bridges(cfg)

    print("CPC Pi-Hub -- %s" % name)
    print("  env    : %s" % (env_path or "(none)"))
    print("  bridges: %d configured" % len(bridges))
    for b in bridges:
        print("    - %s" % b.name)
    if not bridges:
        print("  scaffold: no bridges configured (set UART_DEVICE for the controller bridge)")
        return 0

    # Phase 2 wires the op source (Pluto stream / vacuum route) into the bridges and
    # supervises start()/stop(). For now we report what's configured; the bridge is
    # exercised directly (python3 -m bridges.hid <env>, or dc-test.sh).
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
