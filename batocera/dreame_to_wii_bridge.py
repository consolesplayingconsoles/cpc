#!/usr/bin/env python3
"""
dreame_to_wii_bridge.py — headless launcher for the Dreame -> Wii bridge.

NOTE: Development in progress, fully untested!

The bridge logic now lives in the python client (cpc_python_core.bridge) and is
also exposed as the "Dreame Bridge" menu command. This script just runs it
headless (e.g. as a service) on the batocera master.

Reads peer console envs: ../wii/.env -> BT_MAC, ../dreame/.env -> HOST_IP, TOKEN.
"""
import os
import sys

# The shared client lives at the repo root.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpc-python-client"))
from cpc_python_core.bridges import dreame_wii as bridge


def main():
    wii_mac, vac_ip, vac_token = bridge.config_summary()

    if not vac_ip or not vac_token:
        print("[ERROR] HOST_IP or TOKEN missing in dreame/.env")
        return
    if not wii_mac:
        print("[WARN] BT_MAC missing in wii/.env -- HID reports will be dropped")

    print("[BRIDGE] active  wii={} dreame={}".format(wii_mac or "?", vac_ip))
    bridge.run(
        wii_mac, vac_ip, vac_token,
        should_stop=lambda: False,
        on_status=lambda s: print("[BRIDGE] " + s, end="\r"),
    )


if __name__ == "__main__":
    main()
