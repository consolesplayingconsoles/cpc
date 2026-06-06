import os
import sys
import glob
import math
import select
import struct
import termios
import tty
import time

from core.ui import renderer

# ── Game library ─────────────────────────────────────────────────────────────

def _is_mounted(path):
    """Return True if path is an active mount point per /proc/mounts."""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == path:
                    return True
    except Exception:
        pass
    return False


def _list_games(config, path_key, label):
    """Generic game lister for a configured directory path."""
    path = config.get(path_key, "").strip()
    if not path:
        return ["[{} path not configured]".format(label)]

    # Check mount first — unmounted mount points are empty dirs, not useful
    mount = os.path.dirname(path.rstrip("/"))
    if not _is_mounted(path) and not _is_mounted(mount):
        return ["[disk not mounted — plug in USB drive]"]

    if not os.path.isdir(path):
        return ["[path not found: {}]".format(path)]

    entries = sorted(
        e for e in os.listdir(path)
        if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")
    )
    if not entries:
        return ["[no games found in {}]".format(path)]
    return entries


def list_gc_games(config):
    return _list_games(config, "GC_GAMES_PATH", "GameCube")


def list_wii_games(config):
    return _list_games(config, "WII_GAMES_PATH", "Wii")


# ── Raw /dev/input reader ─────────────────────────────────────────────────────
# Reads Linux input events directly from /dev/input/event* as binary structs.
# No external dependencies — works on any architecture including PowerPC.
#
# Event struct (32-bit kernel, e.g. Wii):
#   struct timeval  { long tv_sec; long tv_usec; }  → 8 bytes (2 × 4-byte long)
#   uint16_t type, code
#   int32_t  value
#   Total: 16 bytes
#
# On 64-bit: timeval is 16 bytes → total 24 bytes.
# We detect the right size at runtime.

_EV_KEY = 1
_EV_ABS = 3

# Button code → name table (subset covering GC / common gamepads)
_BTN_NAMES = {
    0x120: "BTN_TRIGGER",   0x121: "BTN_THUMB",
    0x122: "BTN_THUMB2",    0x123: "BTN_TOP",
    0x124: "BTN_TOP2",      0x125: "BTN_PINKIE",
    0x126: "BTN_BASE",      0x127: "BTN_BASE2",
    0x128: "BTN_BASE3",     0x129: "BTN_BASE4",
    0x12a: "BTN_BASE5",     0x12b: "BTN_BASE6",
    0x12f: "BTN_DEAD",
    0x130: "BTN_SOUTH/A",   0x131: "BTN_EAST/B",
    0x132: "BTN_C",         0x133: "BTN_NORTH/X",
    0x134: "BTN_WEST/Y",    0x135: "BTN_Z",
    0x136: "BTN_TL",        0x137: "BTN_TR",
    0x138: "BTN_TL2",       0x139: "BTN_TR2",
    0x13a: "BTN_SELECT",    0x13b: "BTN_START",
    0x13c: "BTN_MODE",      0x13d: "BTN_THUMBL",
    0x13e: "BTN_THUMBR",
}

_ABS_HAT0X = 0x10
_ABS_HAT0Y = 0x11
_ABS_HAT1X = 0x12
_ABS_HAT1Y = 0x13

_HAT_NAMES = {
    (_ABS_HAT0X, -1): "DPAD_LEFT",   (_ABS_HAT0X, 1): "DPAD_RIGHT",
    (_ABS_HAT0Y, -1): "DPAD_UP",     (_ABS_HAT0Y, 1): "DPAD_DOWN",
    (_ABS_HAT1X, -1): "HAT1_LEFT",   (_ABS_HAT1X, 1): "HAT1_RIGHT",
    (_ABS_HAT1Y, -1): "HAT1_UP",     (_ABS_HAT1Y, 1): "HAT1_DOWN",
}


def _event_format():
    """Return (struct_format, event_size) for this kernel's timeval width."""
    import platform
    bits = 8 * struct.calcsize("l")   # long size = pointer size on Linux
    return ("llHHi", 16) if bits == 32 else ("qqHHi", 24)


def _find_controllers():
    """Return list of (path, name) for likely gamepad /dev/input/event* nodes.
    Accepts devices with BTN keys, ABS axes, or joystick handlers — covers
    native GC ports on the Wii which may not advertise KEY capabilities.
    """
    results = []
    try:
        current = {}
        with open("/proc/bus/input/devices") as f:
            for line in f:
                line = line.strip()
                if line.startswith("N:"):
                    current["name"] = line.split("=", 1)[-1].strip().strip('"')
                elif line.startswith("H: Handlers="):
                    handlers = line.split("=", 1)[-1].split()
                    for h in handlers:
                        if h.startswith("event"):
                            current["event"] = h
                        if h.startswith("js"):
                            current["has_js"] = True
                elif line.startswith("B: KEY="):
                    current["has_key"] = True
                elif line.startswith("B: ABS="):
                    current["has_abs"] = True
                elif line == "":
                    name = current.get("name", "")
                    event = current.get("event")
                    is_input = current.get("has_key") or current.get("has_abs") or current.get("has_js")
                    is_kbd = "keyboard" in name.lower() or "kbd" in name.lower() or "mouse" in name.lower()
                    if event and is_input and not is_kbd:
                        path = "/dev/input/" + event
                        if os.path.exists(path):
                            results.append((path, name or event))
                    current = {}
    except Exception:
        pass
    return results


def controller_test(config: dict):
    """Enter the controller button intercept mode.
    Reads raw /dev/input events — no external dependencies.
    Returns None (owns its own render loop).
    """
    if not os.path.isdir("/dev/input"):
        renderer.render_controller(config, "no /dev/input on this platform", [])
        time.sleep(2)
        return None

    controllers = _find_controllers()
    if not controllers:
        renderer.render_controller(config, "no controllers detected", [])
        time.sleep(2)
        return None

    path, name = controllers[0]
    fmt, size   = _event_format()
    events      = []   # list of (label, code, pressed)

    try:
        dev_f  = open(path, "rb")
        tty_f  = open("/dev/tty", "rb", buffering=0)
        fd_dev = dev_f.fileno()
        fd_kbd = tty_f.fileno()
        old    = termios.tcgetattr(fd_kbd)
        try:
            tty.setraw(fd_kbd)
            while True:
                renderer.render_controller(config, name, events)
                readable, _, _ = select.select([fd_dev, fd_kbd], [], [], 0.1)

                if fd_kbd in readable:
                    ch = os.read(fd_kbd, 1)
                    if ch in (b'q', b'\x03', b'\x1b'):
                        break

                if fd_dev in readable:
                    raw = dev_f.read(size)
                    if len(raw) < size:
                        continue
                    _, _, ev_type, code, value = struct.unpack(fmt, raw)

                    if ev_type == _EV_KEY and value in (0, 1):
                        label = _BTN_NAMES.get(code, "BTN_0x{:03x}".format(code))
                        events.append((label, code, value == 1))

                    elif ev_type == _EV_ABS and (code, value) in _HAT_NAMES and value != 0:
                        events.append((_HAT_NAMES[(code, value)], code, True))
        finally:
            termios.tcsetattr(fd_kbd, termios.TCSADRAIN, old)
    except Exception as e:
        renderer.render_controller(config, "error: {}".format(e), [])
        time.sleep(3)
    finally:
        try: dev_f.close()
        except: pass
        try: tty_f.close()
        except: pass

    return None


# ── Bongo Censor ──────────────────────────────────────────────────────────────

_MIC_CANDIDATES = ["/dev/gcn-mic", "/dev/gcnmic", "/dev/gcn-mic0"]


def _beep(freq=880, duration=0.18):
    """Write a short square wave beep to /dev/dsp (OSS, 8-bit unsigned 8kHz)."""
    rate    = 8000
    samples = int(rate * duration)
    half    = max(1, rate // (freq * 2))
    buf     = bytearray(samples)
    for i in range(samples):
        vol    = 1.0 - max(0.0, (i - samples * 0.8) / (samples * 0.2))
        buf[i] = int(200 * vol) if (i // half) % 2 == 0 else int(55 + 55 * vol)
    try:
        fd = os.open("/dev/dsp", os.O_WRONLY)
        os.write(fd, bytes(buf))
        os.close(fd)
    except Exception as e:
        # surface temporarily so we can diagnose
        import sys
        print("\r  [beep error] {}".format(e), file=sys.stderr)


def _find_mic():
    for path in _MIC_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def bongo_censor(config: dict):
    """Bongo Censor — listens via gcn-mic and beeps back at any sound.
    Wii-exclusive. Returns None (owns its own loop).
    """
    mic_path   = _find_mic()
    tty_f      = open("/dev/tty", "rb", buffering=0)
    fd_kbd     = tty_f.fileno()
    old        = termios.tcgetattr(fd_kbd)
    reaction    = ""
    last_render = None
    cooldown    = 0.0
    THROTTLE    = 0.6
    r_idx       = [0]

    def next_reaction():
        r = renderer._CENSOR_REACTIONS[r_idx[0] % len(renderer._CENSOR_REACTIONS)]
        r_idx[0] += 1
        return r

    def render_if_changed(r):
        nonlocal last_render
        if r != last_render:
            renderer.render_censor(config, r, bool(mic_path))
            last_render = r

    try:
        tty.setraw(fd_kbd)
        mic_f  = open(mic_path, "rb", buffering=0) if mic_path else None
        fd_mic = mic_f.fileno() if mic_f else None

        render_if_changed("")

        while True:
            triggered = False
            fds = [fd_kbd] + ([fd_mic] if fd_mic else [])
            readable, _, _ = select.select(fds, [], [], 0.05)

            if fd_kbd in readable:
                ch = os.read(fd_kbd, 1)
                if ch in (b'q', b'\x03', b'\x1b'):
                    break
                if ch == b' ' and not mic_f and time.time() > cooldown:
                    triggered = True

            if fd_mic and fd_mic in readable:
                raw = mic_f.read(64)
                if raw:
                    level = max(abs(b - 128) for b in bytearray(raw))
                    if level > 30 and time.time() > cooldown:
                        triggered = True

            if triggered:
                cooldown = time.time() + THROTTLE
                reaction = next_reaction()
                render_if_changed(reaction)
                _beep()
            elif reaction and time.time() > cooldown:
                render_if_changed("")
                reaction = ""

    finally:
        termios.tcsetattr(fd_kbd, termios.TCSADRAIN, old)
        tty_f.close()
        if mic_f:
            mic_f.close()

    return None
