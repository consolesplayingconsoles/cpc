import os
import select
import termios
import tty
import time
import threading

from cpc_python_core.ui import renderer
from cpc_python_core import chat as chat_mod
from cpc_python_core.bridges import dreame_wii

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
    except Exception:
        pass


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


# ── Group Chat ────────────────────────────────────────────────────────────────

def chat_view(config: dict):
    """Full-screen group chat against the Pluto API.

    ESC / Ctrl+C (when idle)  → exit to menu
    Ctrl+C (during expansion)  → kill subprocess, stay in chat
    Ctrl+R                     → force refresh
    Enter                      → send draft (expanding {{ cmd }} first)
    Backspace                  → delete last char
    Returns None.
    """
    pluto_ip  = config.get("PLUTO_IP", "").strip()
    pluto_url = "http://%s:7700" % pluto_ip
    sender    = config.get("NODE_NAME", config.get("SHORT_NAME", "console")).lower()

    tty_f  = open("/dev/tty", "rb", buffering=0)
    fd_tty = tty_f.fileno()
    old    = termios.tcgetattr(fd_tty)

    messages        = []
    last_id         = 0
    draft           = ""
    status          = ""
    POLL_S          = 5.0
    last_full_state = None   # (len(messages), status) — triggers full redraw
    last_draft      = None   # triggers input-line-only update

    def fetch():
        nonlocal last_id
        new = chat_mod.fetch_messages(pluto_url, since=last_id)
        if new:
            messages.extend(new)
            last_id = new[-1]["id"]

    fetch()

    try:
        tty.setraw(fd_tty)
        last_poll = time.time()

        while True:
            full_state = (len(messages), status)
            if full_state != last_full_state:
                renderer.render_chat(config, messages, draft, status)
                last_full_state = full_state
                last_draft = draft
            elif draft != last_draft:
                renderer.update_chat_input(config, draft, status)
                last_draft = draft

            r, _, _ = select.select([fd_tty], [], [], 0.5)

            now = time.time()
            if now - last_poll > POLL_S:
                fetch()
                last_poll = now
                status = ""

            if not r:
                continue

            ch = os.read(fd_tty, 1)

            # ESC — bare ESC exits; arrow/function sequences are ignored
            if ch == b'\x1b':
                r2, _, _ = select.select([fd_tty], [], [], 0.05)
                if r2:
                    os.read(fd_tty, 8)   # flush the sequence bytes
                else:
                    break                # bare ESC → exit chat
                continue

            # Ctrl+C when idle → exit chat
            if ch == b'\x03':
                break

            # Ctrl+R → manual refresh
            if ch == b'\x12':
                fetch()
                last_poll = time.time()
                status = "refreshed"
                continue

            # Enter → send
            if ch in (b'\r', b'\n'):
                text = draft.strip()
                draft = ""
                status = ""
                if not text:
                    continue

                if chat_mod.has_expansion(text):
                    interrupt = threading.Event()
                    result    = [None]

                    def _expand(t=text, ev=interrupt, out=result):
                        out[0] = chat_mod.expand_shell(t, ev)

                    t = threading.Thread(target=_expand)
                    t.start()
                    status = "expanding...  Ctrl+C to cancel"

                    while t.is_alive():
                        last_full_state = None  # force redraw so status updates are visible
                        renderer.render_chat(config, messages, draft, status)
                        r2, _, _ = select.select([fd_tty], [], [], 0.2)
                        if r2:
                            c2 = os.read(fd_tty, 1)
                            if c2 == b'\x03':
                                interrupt.set()

                    t.join()

                    if interrupt.is_set():
                        status = "interrupted"
                        continue

                    text   = result[0] or ""
                    status = ""

                if text.strip():
                    ok, err = chat_mod.post_message(pluto_url, sender, text)
                    if ok:
                        fetch()
                        last_poll = time.time()
                    else:
                        status = "send failed: %s" % err
                continue

            # Backspace
            if ch in (b'\x7f', b'\x08'):
                draft = draft[:-1]
                continue

            # Printable ASCII
            try:
                c = ch.decode('ascii')
                if c.isprintable():
                    draft += c
            except (UnicodeDecodeError, ValueError):
                pass

    finally:
        termios.tcsetattr(fd_tty, termios.TCSADRAIN, old)
        tty_f.close()

    return None


def dreame_wii_view(config):
    """Live Dreame L40 -> Wii bridge: the vacuum's motion drives a Wii game.

    Runs the bridge loop in a daemon thread while this view is open, streaming
    status to the screen. q / ESC stops it and returns to the menu.
    """
    wii_mac, vac_ip, vac_token = dreame_wii.config_summary()

    status_lines = []
    stop = threading.Event()

    def on_status(text):
        status_lines.append(text)
        del status_lines[:-8]   # keep the last 8

    if not dreame_wii.miio_installed():
        status_lines.append("miio not installed on this node -- bridge unavailable.")
    elif not (wii_mac and vac_ip and vac_token):
        status_lines.append("missing config: need wii BT_MAC + dreame HOST_IP/TOKEN.")
    else:
        status_lines.append("connecting to L40 at %s ..." % vac_ip)
        threading.Thread(
            target=dreame_wii.run,
            args=(wii_mac, vac_ip, vac_token, stop.is_set, on_status),
            daemon=True,
        ).start()

    tty_f  = open("/dev/tty", "rb", buffering=0)
    fd_tty = tty_f.fileno()
    old    = termios.tcgetattr(fd_tty)
    try:
        tty.setraw(fd_tty)
        last = None
        while True:
            snap = tuple(status_lines)
            if snap != last:
                renderer.render_bridge(config, "Dreame L40 -> Wii", list(snap))
                last = snap
            r, _, _ = select.select([fd_tty], [], [], 0.2)
            if r:
                ch = os.read(fd_tty, 1)
                if ch in (b'q', b'\x1b', b'\x03'):
                    break
    finally:
        stop.set()
        termios.tcsetattr(fd_tty, termios.TCSADRAIN, old)
        tty_f.close()

    return None
