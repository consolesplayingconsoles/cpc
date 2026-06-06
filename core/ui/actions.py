import os
import sys
import select
import termios
import tty
import time

from core.ui import renderer

# evdev is Linux-only. Import gracefully so the menu doesn't crash on macOS.
try:
    import evdev
    from evdev import ecodes
    _HAS_EVDEV = True
except ImportError:
    _HAS_EVDEV = False


def _find_controllers():
    """Return all /dev/input devices that expose gamepad/joystick buttons."""
    devices = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            caps = d.capabilities()
            keys = caps.get(ecodes.EV_KEY, [])
            # Any device with at least one BTN_ code in the gamepad/joystick ranges
            if any(
                ecodes.BTN_MISC <= k <= ecodes.BTN_GEAR_UP
                or ecodes.BTN_GAMEPAD <= k <= ecodes.BTN_THUMBR
                for k in keys
            ):
                devices.append(d)
        except Exception:
            pass
    return devices


def controller_test(config: dict):
    """Enter the controller button intercept mode.
    Returns None (owns its own render loop) so the main menu regains
    control when the user exits.
    """
    if not _HAS_EVDEV:
        # Graceful no-op on non-Linux (macOS dev machine etc.)
        renderer.render_controller(config, "evdev not available on this platform", [])
        time.sleep(2)
        return None

    controllers = _find_controllers()
    if not controllers:
        renderer.render_controller(config, "no controllers detected", [])
        time.sleep(2)
        return None

    # Use the first detected controller. A picker can be added later if needed.
    device = controllers[0]

    events = []   # list of (name, code, pressed)

    fd_kbd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd_kbd)
    try:
        tty.setraw(fd_kbd)
        while True:
            renderer.render_controller(config, device.name, events)

            readable, _, _ = select.select([device.fd, fd_kbd], [], [], 0.1)

            if fd_kbd in readable:
                ch = os.read(fd_kbd, 1)
                if ch in (b'q', b'\x03', b'\x1b'):   # q, Ctrl-C, ESC
                    break

            if device.fd in readable:
                for ev in device.read():
                    if ev.type == ecodes.EV_KEY and ev.value in (0, 1):
                        # Face buttons, triggers, shoulders, etc.
                        name = ecodes.KEY.get(ev.code) or ecodes.BTN.get(ev.code) or str(ev.code)
                        if isinstance(name, list):
                            name = name[0]
                        events.append((name, ev.code, ev.value == 1))
                    elif ev.type == ecodes.EV_ABS and ev.code in (
                        ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y,
                        ecodes.ABS_HAT1X, ecodes.ABS_HAT1Y,
                    ) and ev.value != 0:
                        # D-pad (HAT axes). Skip value==0 (release/centre) to
                        # keep the log readable — direction is what matters.
                        axis  = ecodes.ABS.get(ev.code, str(ev.code))
                        if isinstance(axis, list):
                            axis = axis[0]
                        label = {
                            (ecodes.ABS_HAT0X, -1): "DPAD_LEFT",
                            (ecodes.ABS_HAT0X,  1): "DPAD_RIGHT",
                            (ecodes.ABS_HAT0Y, -1): "DPAD_UP",
                            (ecodes.ABS_HAT0Y,  1): "DPAD_DOWN",
                            (ecodes.ABS_HAT1X, -1): "HAT1_LEFT",
                            (ecodes.ABS_HAT1X,  1): "HAT1_RIGHT",
                            (ecodes.ABS_HAT1Y, -1): "HAT1_UP",
                            (ecodes.ABS_HAT1Y,  1): "HAT1_DOWN",
                        }.get((ev.code, ev.value), f"{axis}:{ev.value}")
                        events.append((label, ev.code, True))
    finally:
        termios.tcsetattr(fd_kbd, termios.TCSADRAIN, old_settings)

    return None
