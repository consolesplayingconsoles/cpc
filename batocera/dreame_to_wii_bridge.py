#!/usr/bin/env python3
"""

NOTE: Development in progress, fully untested!

dreame_to_wii_bridge.py — reads the Dreame vacuum's live telemetry and
translates heading + cleaning state into Wii Bluetooth HID input reports.

Reads sibling console env files (same convention as Pluto):
  ../wii/.env    -> BT_MAC
  ../dreame/.env -> HOST_IP, TOKEN
"""
import os
import sys
import math
import time
import socket

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.env import sibling_env

from miio import DreameVacuum


def scale_to_joystick(val, min_val, max_val):
    clamped = max(min(val, max_val), min_val)
    normalized = (clamped - min_val) / (max_val - min_val)
    return int(normalized * 255)


def send_raw_wii_hid(wii_mac, joy_x, button_a_pressed):
    if not wii_mac:
        return
    report = bytearray(6)
    report[0] = 0xa1
    report[1] = 0x34
    if button_a_pressed:
        report[2] |= 0x10
    report[4] = joy_x
    try:
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_L2CAP)
        sock.connect((wii_mac, 0x13))
        sock.send(report)
        sock.close()
    except Exception:
        pass


def main():
    wii_cfg    = sibling_env("wii", __file__)
    dreame_cfg = sibling_env("dreame", __file__)

    wii_mac   = wii_cfg.get("BT_MAC", "")
    vac_ip    = dreame_cfg.get("HOST_IP", "")
    vac_token = dreame_cfg.get("TOKEN", "")

    if not vac_ip or not vac_token:
        print("[ERROR] HOST_IP or TOKEN missing in dreame/.env")
        return
    if not wii_mac:
        print("[WARN] BT_MAC missing in wii/.env — HID reports will be dropped")

    print("[BRIDGE] active  wii={} dreame={}".format(wii_mac or "?", vac_ip))

    vac = DreameVacuum(ip=vac_ip, token=vac_token)

    while True:
        try:
            status = vac.status()
            if status.is_docked:
                steering, accelerate = 128, False
            else:
                x_vector  = math.sin(math.radians(getattr(status, "heading", 0)))
                steering   = scale_to_joystick(x_vector, -1.0, 1.0)
                accelerate = status.is_cleaning
            send_raw_wii_hid(wii_mac, steering, accelerate)
            print("[BRIDGE] stick_x={} gas={}".format(steering, accelerate), end="\r")
        except Exception as e:
            print("\n[WARN] {}".format(e))
        time.sleep(0.1)


if __name__ == "__main__":
    main()
