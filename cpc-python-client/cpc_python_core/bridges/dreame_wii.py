"""
cpc_python_core/bridges/dreame_wii.py — Dreame L40 -> Wii HID bridge.

One of the cpc_python_core.bridges family (more device bridges land alongside).
Reads the vacuum's live heading + cleaning state and translates it into Wii
Bluetooth HID joystick reports, so the robot literally drives a Wii game. Wired
up as the "Dreame -> Wii" menu command, and runnable headless via the standalone
launcher in batocera/.

miio (DreameVacuum) is imported LAZILY: it pulls C-extension deps that don't
exist on the constrained consoles (the Wii is PowerPC, no cryptography), so this
module stays importable everywhere. Only run() touches miio, and the menu only
offers it where ready() says it can actually run.
"""
import os
import math
import time
import socket
import importlib.util

from cpc_python_core.env import load_env

# Deploy/repo root holding the console dirs:
#   <root>/cpc-python-client/cpc_python_core/bridges/dreame_wii.py  ->  <root>
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _peer_env(console):
    return load_env(os.path.join(_ROOT, console, ".env"))


def miio_installed():
    """Cheap presence check for the optional miio dep — no import side effects."""
    try:
        return importlib.util.find_spec("miio") is not None
    except Exception:
        return False


def config_summary():
    """(wii_mac, vac_ip, vac_token) pulled from the peer console envs."""
    wii    = _peer_env("wii")
    dreame = _peer_env("dreame")
    return wii.get("BT_MAC", ""), dreame.get("HOST_IP", ""), dreame.get("TOKEN", "")


def ready():
    """True only where the bridge can run: miio present AND both peer envs
    supply what we need (Wii BT MAC + Dreame ip/token)."""
    if not miio_installed():
        return False
    mac, ip, token = config_summary()
    return bool(mac and ip and token)


# ── HID translation ──────────────────────────────────────────────────────────

def scale_to_joystick(val, min_val, max_val):
    clamped = max(min(val, max_val), min_val)
    return int((clamped - min_val) / (max_val - min_val) * 255)


def send_raw_wii_hid(wii_mac, joy_x, button_a_pressed):
    """Send one raw Wii Bluetooth HID input report over L2CAP. Best-effort."""
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


def run(wii_mac, vac_ip, vac_token, should_stop, on_status):
    """Blocking bridge loop. Calls on_status(ascii_text) each tick and stops when
    should_stop() returns True. Lazy-imports miio (call only where installed)."""
    try:
        from miio import DreameVacuum
    except Exception as exc:
        on_status("miio unavailable: %s" % str(exc)[:48])
        return

    try:
        vac = DreameVacuum(ip=vac_ip, token=vac_token)
    except Exception as exc:
        on_status("vacuum init failed: %s" % str(exc)[:48])
        return

    while not should_stop():
        try:
            status = vac.status()
            if getattr(status, "is_docked", False):
                steering, accelerate, state = 128, False, "docked"
            else:
                x_vector   = math.sin(math.radians(getattr(status, "heading", 0)))
                steering   = scale_to_joystick(x_vector, -1.0, 1.0)
                accelerate = bool(getattr(status, "is_cleaning", False))
                state      = "cleaning" if accelerate else "idle"
            send_raw_wii_hid(wii_mac, steering, accelerate)
            on_status("L40 %-8s  stick_x=%-3d  gas=%s"
                      % (state, steering, "on" if accelerate else "off"))
        except Exception as exc:
            on_status("read error: %s" % str(exc)[:40])
        time.sleep(0.1)
