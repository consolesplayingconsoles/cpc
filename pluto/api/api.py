#!/usr/bin/env python3
"""
api.py — local API server for Pluto.
Handles network pings, deploy triggers, and group chat messages.
Listens on all interfaces so LAN clients (consoles) can reach it.

Usage: python3 api/api.py
"""
import os
import sys
import json
import platform
import subprocess
import http.server
import socketserver
import urllib.parse
import threading
import time
import random
import re
import atexit
import signal
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Feature APIs live under modules/ (one package per integration). Aliased so the
# rest of this file keeps calling dreame_session.* / vacuum.* unchanged.
from modules.dreame import session as dreame_session
from modules.dreame import commands as vacuum
from modules.substack import sender as substack


def open_path(path):
    """Open a file or directory in the system file manager, cross-platform."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", path])
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path])
    elif system == "Windows":
        subprocess.Popen(["explorer", path])


PORT = 7700


# ── @claude bot (Anthropic API) ──────────────────────────────────────────────
# Claude as a guest in the chat, running on the operator's own Anthropic API key.
# When the key rate-limits or runs out of credit the bot just blinks OFFLINE for
# a cooldown and posts a short "broke" line — that intermittency is the joke, not
# a bug. The key lives on Pluto only and is never deployed to consoles. Disabled
# entirely when ANTHROPIC_API_KEY is unset, so the project ships clean for others.
BOT_ID         = "claude"
_bot_key       = None
_bot_broke     = False   # keyless gag mode: always broke, no API call, no cost
_bot_model     = "claude-haiku-4-5-20251001"   # cheap + fast; override via env
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Epoch seconds until which the bot is considered offline (rate-limited / broke).
# 0 means online. Auto-recovers after the cooldown so it can be poked again.
_bot_offline_until = 0.0
_BOT_COOLDOWN      = 60

_BOT_SYSTEM = (
    "You are Claude, a guest in the group chat of CPC (Consoles Playing "
    "Consoles) -- a home LAN of retro consoles (Wii, Dreamcast, PS3, GBA, "
    "WonderSwan, Batocera) run by their human operators. Pluto is the admin "
    "dashboard, not a console. You run on the operator's own Anthropic API key, "
    "so you blink offline the moment their credits or rate limits run dry -- "
    "lean into being the broke, intermittent option, like an arcade cabinet "
    "that ate someone's quarter. Tone: concise, technical, geeky, dry, "
    "self-aware. One or two sentences. ASCII only -- no emoji or unicode, your "
    "messages also render on bare console terminals. You are @claude."
)

# ASCII-only on purpose: these can be fetched and rendered by the console TUIs.
_BOT_AWAY = [
    "out of continues. INSERT COIN to continue.",
    "brb, the api credits ran dry.",
    "402 Payment Required... jk, the operator's just broke.",
    "rate limited. respawning shortly.",
    "afk -- tokens need a nap.",
    "GAME OVER. high score stands. ping me later.",
]


def _bot_set_offline():
    global _bot_offline_until
    _bot_offline_until = time.time() + _BOT_COOLDOWN


def _bot_online():
    return time.time() >= _bot_offline_until


def _bot_enabled():
    """The @claude member shows up for a real key OR for the keyless gag."""
    return bool(_bot_key) or _bot_broke


def _bot_reply(messages_snapshot):
    """Dispatch a mention to the real Claude, or the keyless broke-mode gag."""
    if not _bot_key:
        # Broke mode: no key, no API call, no cost -- just the joke, then it
        # "breaks" and blinks offline for the cooldown like a fed-up arcade box.
        _bot_set_offline()
        _new_message(BOT_ID, random.choice(_BOT_AWAY))
        return
    _claude_reply(messages_snapshot)


def _claude_reply(messages_snapshot):
    """Call the Anthropic API with recent chat context, post the reply as 'claude'.

    Runs in a background daemon thread. On a rate-limit / out-of-credit / overload
    the bot posts a short in-character 'broke' line and flips OFFLINE for a
    cooldown, so it shows as a down node until it auto-recovers and gets poked.
    Config (401/400) failures surface a real diagnostic instead of a joke.
    """
    global _bot_offline_until

    # Flatten the recent chat into one user turn — avoids the Messages API's
    # role-alternation rules while still giving Claude the full conversation.
    transcript = "\n".join(
        "%s: %s" % (m["sender"], m["text"]) for m in messages_snapshot[-15:]
    )
    user_content = (
        "Here is the recent CPC group chat. Reply as 'claude' to the latest "
        "message that mentions you. Do not prefix your reply with your own name.\n\n"
        + transcript
    )

    payload = {
        "model":      _bot_model,
        "max_tokens": 300,
        "system":     _BOT_SYSTEM,
        "messages":   [{"role": "user", "content": user_content}],
    }
    req = Request(
        _ANTHROPIC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key":         _bot_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
    )
    try:
        resp  = urlopen(req, timeout=30)
        data  = json.loads(resp.read().decode("utf-8"))
        parts = data.get("content", [])
        reply = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        # Strip any non-ASCII before it can reach a console terminal.
        reply = reply.encode("ascii", "ignore").decode("ascii").strip()
        if not reply:
            reply = random.choice(_BOT_AWAY)
        _bot_offline_until = 0.0
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "ignore")
        except Exception:
            pass
        print("  [claude] HTTP %d (model=%s): %s" % (exc.code, _bot_model, body[:300]))
        low_credit = exc.code == 400 and "credit" in body.lower()
        if exc.code in (429, 529) or low_credit:
            # Transient / broke — the intended "flaky bot" state.
            _bot_set_offline()
            reply = random.choice(_BOT_AWAY)
        elif exc.code == 401:
            reply = "claude can't auth -- check ANTHROPIC_API_KEY in pluto/.env."
        else:
            reply = "claude glitched (HTTP %d). check the pluto server log." % exc.code
    except Exception as exc:
        print("  [claude] error: %s" % exc)
        _bot_set_offline()
        reply = random.choice(_BOT_AWAY)

    _new_message(BOT_ID, reply)


def _substack_post(creds, content):
    """Background worker: turn an @substack post into a draft, reply as 'substack'.
    Runs off-thread (login + draft are network IO) so POST /messages doesn't block."""
    ok, msg = substack.post(creds, content)
    _new_message("substack", msg)


def _is_allowed_origin(origin):
    """Allow localhost (incl. multi-label *.localhost like pluto.localhost and
    pluto.dev.localhost) and RFC-1918 LAN."""
    if re.match(r'^https?://(localhost|127\.0\.0\.1|([a-z0-9-]+\.)+localhost)(:\d+)?$', origin):
        return True
    # 192.168.x.x, 10.x.x.x, 172.16-31.x.x
    if re.match(
        r'^https?://(192\.168\.\d{1,3}\.\d{1,3}'
        r'|10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        r'|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})'
        r'(:\d+)?$',
        origin
    ):
        return True
    return False


def _is_lan_ip(ip):
    """True for loopback or an RFC-1918 private address -- i.e. a request from the
    trusted local network. Used to gate the Dreame login: on a home LAN it's
    reasonable to sign in from a phone or another machine, not just the box itself."""
    ip = ip.replace("::ffff:", "")   # unwrap IPv4-mapped IPv6
    if ip in ("127.0.0.1", "::1"):
        return True
    return bool(re.match(
        r'^(192\.168\.\d{1,3}\.\d{1,3}'
        r'|10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        r'|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})$',
        ip
    ))


REQUIRED_VARS = ["GATEWAY_IP"]

# The node roster is DISCOVERED at startup from <repo>/nodes/local/*/ (pinged LAN
# nodes) and <repo>/nodes/cloud/*/ (off-network connectors: status 'cloud', never
# pinged, always shown), keyed by dir name, plus 'pluto' the host. See
# discover_nodes(). No hardcoded list, no per-request rescans -- the startup
# snapshot is the single source of truth.

# Consoles whose OS is fixed by definition — used as the badge default so it shows
# even when the node is offline (TTL detection only works on a live reply).
# Batocera is a Linux distro, full stop. The Wii is deliberately absent: it may run
# Wii Linux today and a native homebrew .dol tomorrow, so we let it be detected.
KNOWN_OS = {"batocera": "linux", "pi": "linux"}

# ── In-memory message store ──────────────────────────────────────────────────
# Ephemeral by design: cleared on restart.
# Append-logged to _log_path (set at startup) for historical reference.
_messages = []   # list of dicts
_msg_seq  = 0    # auto-increment id
_log_path = None # absolute path to messages.log, or None if unavailable


def _new_message(sender, text):
    global _msg_seq
    _msg_seq += 1
    msg = {
        "id":     _msg_seq,
        "sender": sender,
        "text":   text.strip(),
        "ts":     datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _messages.append(msg)
    _log_message(msg)
    return msg


def _get_messages(since=None):
    """Return messages with id > since (or all if since is None)."""
    if since is None:
        return list(_messages[-200:])
    return [m for m in _messages if m["id"] > since]


def _log_message(msg):
    if _log_path:
        try:
            with open(_log_path, "a") as f:
                f.write(json.dumps(msg) + "\n")
        except Exception:
            pass


# How many recent messages to restore from the log on boot. The feed is otherwise
# in-memory (cleared on restart/deploy); this just rehydrates the tail so a deploy
# doesn't wipe the conversation. No pagination -- older history lives in the log.
STARTUP_MESSAGES = 50


def _load_recent_messages(limit=STARTUP_MESSAGES):
    """Repopulate the in-memory feed from the tail of the on-disk log, so the chat
    survives a restart. A log line needs only `sender` and `text` -- `id` is
    reassigned and `ts` defaults to now, so history can be hand-fabricated by just
    typing those two fields per line."""
    global _msg_seq
    if not _log_path or not os.path.exists(_log_path):
        return
    try:
        with open(_log_path) as f:
            lines = f.readlines()[-limit:]
    except Exception:
        return
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    loaded = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(m, dict) and m.get("sender") and "text" in m:
            loaded.append(m)
    if loaded:
        # Don't trust ids/timestamps in the log: older runs each restarted numbering
        # at 1 (so ids aren't unique), and fabricated history may omit them entirely.
        # Renumber into one clean monotonic sequence (file order = chronological) so
        # the frontend's keys and since-polling stay correct; backfill missing ts.
        for i, m in enumerate(loaded, start=1):
            m["id"] = i
            if not m.get("ts"):
                m["ts"] = now
        _messages[:] = loaded
        _msg_seq = len(loaded)


# ── Shared helpers ───────────────────────────────────────────────────────────

def console_env_path(base_dir, node_id):
    """Path to a node's REAL .env -- used where the live config file is needed
    (e.g. the deploy stream). pluto is the host: its .env is pluto/.env (base_dir
    itself). Deployable consoles live under <repo>/nodes/local/<name>/.env. (Cloud
    connectors aren't deployed, so they never reach here.)"""
    if node_id == "pluto":
        return os.path.join(base_dir, ".env")
    return os.path.normpath(os.path.join(base_dir, "..", "nodes", "local", node_id, ".env"))


def discover_nodes(base_dir):
    """Discover the node roster ONCE at startup from <repo>/nodes/, keyed by dir name:

      nodes/local/<name>/  -- a pinged LAN node (console/host). Tagged _kind='local'.
      nodes/cloud/<name>/  -- an off-network connector (cloud drive, LLM agent,
                              DreameHome, Substack). Tagged _kind='cloud': never
                              pinged. Configured (a real .env present) -> shown;
                              placeholder (only .env.sample) -> 'unconfigured', so
                              it hides behind the same toggle as placeholder LAN
                              nodes. (The 'cloud' hub is virtual, synthesised in
                              _build_nodes -- no dir, like 'gateway'.)

    Each node's config comes from its dir's .env (configured) or, if absent, its
    .env.sample (an unconfigured placeholder slot). A dir with NEITHER is malformed
    -> fail fast. Returns {name: config} with cfg['_kind'] and cfg['_has_env']
    tagged. (pluto, the host, is added by the caller from the main pluto/.env.) This
    snapshot is the single source of truth; nothing rescans the filesystem after."""
    roster = {}
    nodes_root = os.path.normpath(os.path.join(base_dir, "..", "nodes"))
    for kind in ("local", "cloud"):
        kind_root = os.path.join(nodes_root, kind)
        if not os.path.isdir(kind_root):
            continue
        for name in sorted(os.listdir(kind_root)):
            d = os.path.join(kind_root, name)
            if name.startswith(".") or not os.path.isdir(d):
                continue
            env_f, sample_f = os.path.join(d, ".env"), os.path.join(d, ".env.sample")
            has_env = os.path.exists(env_f)
            if has_env:
                cfg = load_env(env_f)
            elif os.path.exists(sample_f):
                cfg = load_env(sample_f)   # placeholder identity; unconfigured
            else:
                print("\n  ERROR: node dir has no .env or .env.sample: %s\n" % d)
                sys.exit(1)
            cfg["_kind"]    = kind
            cfg["_has_env"] = has_env
            roster[name]    = cfg
    return roster


def parse_pico(value):
    """A PICO_<chipid> .env value -> a fields dict. Accepts the structured form
    'role=hid,conn=usb,managed=python' or the bare role shorthand 'hid'. (Mirrors
    pluto-pi-hub/propagate.py; the two packages can't share code.)"""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1].strip()        # tolerate a quoted .env value
    if "=" not in value:
        return {"role": value} if value else {}
    out = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def picos_from_env(cfg, fw_root=None):
    """Every PICO_<chipid>=... line in a node's .env -> a list the UI can render.

    Declared fields (role, conn, dev, baud) pass through verbatim -- NO assumed
    defaults, so what isn't declared reads as 'unspecified' rather than a fabricated
    'usb'. `deploy` is DERIVED, never declared: a board is pluto-deployed IFF its role
    has firmware here -- the exact condition propagate.py flashes on -- so the badge
    reflects what pluto ACTUALLY does, not a flag that can drift. '' when we can't see
    the firmware tree (a deployed node without the hub checkout). In .env declaration
    order (load_env preserves file order), so the UI mirrors the .env top-to-bottom."""
    out = []
    for k in cfg:
        if not k.startswith("PICO_"):
            continue
        spec = parse_pico(cfg[k])
        role = spec.get("role", "")
        deploy = ""
        if fw_root and role:
            deploy = "pluto" if os.path.exists(os.path.join(fw_root, role, "main.py")) else "pi"
        out.append({
            "chipid": k[len("PICO_"):],
            "alias":  spec.get("alias", ""),    # human label (sega, nintendo) -- the rename-in-Pluto handle
            "iface":  spec.get("iface", ""),    # USB profile the board presents: ps3 | switch | xinput ...
            "role":   role,
            "conn":   spec.get("conn", ""),     # usb | uart -- empty if not declared
            "dev":    spec.get("dev", ""),
            "baud":   spec.get("baud", ""),
            "deploy": deploy,                   # DERIVED: pluto (firmware present) | pi (local) | '' (unknown)
        })
    return out


def probe(ip):
    """Reach a host and infer a coarse OS family from the reply TTL.

    More than a plain up/down ping: Linux/macOS/BSD stamp packets with a default
    TTL of 64, Windows 128, network gear 255. On a LAN (0-1 hops) that survives
    intact, so it's a free, zero-config OS hint — no agent, no SSH, no MAC trick
    (a MAC only identifies the NIC vendor, never the OS).

    Returns (up: bool, os: str|None) where os is 'linux' | 'windows' | None.
    Note TTL 64 can't tell Linux from macOS/BSD apart — it means "unix-like";
    on this network the remote unix nodes are the Linux consoles, and the macOS
    host is detected locally instead. The `.env` OS= var overrides when wrong.
    """
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            text=True,
        )
    except Exception:
        return False, None
    if result.returncode != 0:
        return False, None
    m   = re.search(r"ttl[=\s]*(\d+)", result.stdout, re.IGNORECASE)
    ttl = int(m.group(1)) if m else None
    if ttl is None:
        return True, None
    if ttl <= 64:
        return True, "linux"     # unix-like — the Linux consoles on this LAN
    if ttl <= 128:
        return True, "windows"
    return True, None            # ~255 = routers / network gear, no badge


def probe_many(ips):
    """Probe several hosts at once. Each probe() blocks up to ~2s on a down host,
    so doing them in series made /nodes take (down-hosts x 2s) -- the slow first
    render. One thread per ip collapses that to a single ~2s wait. Pure-stdlib
    threads (fine on the constrained nodes). Returns {ip: (up, os)}."""
    results = {}
    threads = []
    for ip in set(filter(None, ips)):
        def work(ip=ip):
            results[ip] = probe(ip)
        t = threading.Thread(target=work)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return results


def _detect_os(env, fallback=None):
    """OS for a node: explicit `.env` override (OS= or PLATFORM=) wins, else the
    value sniffed from the probe. Set OS=native on a homebrew build to hide Tux."""
    return (env.get("OS", "").strip().lower()
            or env.get("PLATFORM", "").strip().lower()
            or fallback)


def load_env(path):
    config = {}
    if not os.path.exists(path):
        return config
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            config[k.strip()] = v
    return config


# ── Client identity ──────────────────────────────────────────────────────────
# Who is a requester? Source IP -> known node (from the env HOST_IPs), else a
# User-Agent signature (closed system: one of each console), else "guest".
# Server-authoritative: the browser clients never set their own sender.

_UA_NODE_SIGNATURES = [
    ("nintendo wii",  "wii"),
    ("dreamcast",     "dc"),
    ("playstation 3", "ps3"),
]


def ip_to_node(roster, config, is_lab=False, lab_ip=""):
    """Build {ip: node_id} from the discovered roster. Localhost maps to the SELF
    instance -- 'lab' on the workspace, else 'pluto' (the C2) -- so QAing from the
    box you're running identifies you correctly. HOST_IP is always the C2; LAB_IP
    (when known) is the Lab, so the lab machine reads as 'lab' from either side."""
    self_id = "lab" if is_lab else "pluto"
    mapping = {"127.0.0.1": self_id, "::1": self_id}
    host_ip = config.get("HOST_IP", "").strip()
    if host_ip:
        mapping[host_ip] = "pluto"
    if lab_ip:
        mapping[lab_ip] = "lab"
    for name, cfg in roster.items():
        ip = cfg.get("HOST_IP", "").strip()
        if ip:
            mapping[ip] = name
    return mapping


def node_for_ua(ua):
    low = (ua or "").lower()
    for sig, node in _UA_NODE_SIGNATURES:
        if sig in low:
            return node
    return None


def _mention_index(roster, chat_config):
    """Chat mention maps from the LIVE roster: every node is taggable. A node's
    @handle defaults to its key; chat.json mentions.handles overrides it (e.g.
    dreame -> l40). Returns (by_id, to_node): {node_id: handle} and
    {'@handle': node_id} (lowercased). gateway/cloud are virtual and not in the
    roster, so the list is naturally just the real chat participants."""
    handles = (chat_config or {}).get("mentions", {}).get("handles", {})
    by_id   = {nid: handles.get(nid, nid) for nid in roster}
    to_node = {("@" + h).lower(): nid for nid, h in by_id.items()}
    return by_id, to_node


# ── Robutek drive: dev-only vacuum-replay -> emulator/console output ──────────
# The Pluto playback clock drives a controller Sink. The engine lives in api/drive/
# (controller + the dreame route->event adapter); it's imported lazily because the one
# working sink (KeyboardSink) needs pynput + macOS Accessibility -- so this whole
# feature degrades to a clean JSON error anywhere but the dev Mac.
_drive_lock  = threading.Lock()
_drive_state = {"sink": None, "thread": None, "stop": None, "last_seen": 0.0,
                "live_target": None}
DRIVE_TIMEOUT = 6.0   # stop the drive if the frontend hasn't checked in for this long


def _control_log_path():
    """The WAIT/GO collaboration log -- a gitignored JSONL file (logs/*.log) that the
    chat-agreed 'Claude plays the console' flow tails: GO = play, WAIT = stop. The
    Claude source's big button appends here; Pluto only logs, it drives nothing off it.
    Rooted at pluto/logs/ so it sits beside the app, never committed."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.normpath(os.path.join(d, "control.log"))


# ── HDMI capture: the WHOLE point of the Claude source ────────────────────────
# Claude plays a console; to *see* what's happening it reads a still frame off the
# HDMI capture card. Claude is NOT allowed to start that capture itself -- Pluto owns
# the camera lifecycle, and that ownership IS the abstraction/safety boundary. The
# operator's GO starts a persistent ffmpeg that overwrites one rolling JPEG
# (dist/latest.jpg); Claude only ever READS that file.
#
# Lifecycle is governed by a KILL-SWITCH FILE: dist/capture.flag (a tiny JSON
# {"state","ts","by"}). Anyone may write it -- Pluto on GO, the open page as a
# heartbeat, Claude bumping it on each frame read, or a manual Stop. A watchdog polls
# it and kills ffmpeg when it reads "stop" or goes STALE (no refresh within
# CAPTURE_STALE_SECS = everyone walked away). This is idle-on-read without trusting
# the OS atime: the reader self-reports by touching the flag.
_capture_lock  = threading.Lock()
_capture_state = {"proc": None, "thread": None, "stop": None, "device": None, "started": 0.0}
CAPTURE_STALE_SECS  = 180.0   # no flag refresh for this long => the session ended; stop
# HARD PRIVACY RULE (paramount): capture is ONLY ever a real (non-camera) capture device,
# matched BY NAME -- the NAME is the guarantee, the index is NOT (it shifts between sessions,
# so "never index 0" was wrong and is gone). Prefer this card; never a camera/mic.
CAPTURE_DEVICE_NAME = os.environ.get("CAPTURE_DEVICE_NAME", "USB3 Video")

# NOGO KEYWORDS (user rule, 2026-06-21): the camera check applies to EVERY device -- any
# whose name contains one of these is NEVER a valid source, whatever CAPTURE_DEVICE_NAME
# says and whatever index it sits at. If every input is a camera, capture FAILS rather than
# ever falling back to one.
CAPTURE_NOGO_KEYWORDS = ("camera", "facetime", "built-in", "builtin", "microphone")
# Screen-grab inputs ("Capture screen N") are non-camera but they record the DESKTOP, not
# the console feed -- excluded from the auto-fallback so GO can never silently film the
# screen. (Set CAPTURE_ALLOW_SCREEN=1 to include them.)
CAPTURE_SCREEN_KEYWORDS = ("capture screen",)

def _capture_name_forbidden(dev_name):
    low = (dev_name or "").lower()
    return any(k in low for k in CAPTURE_NOGO_KEYWORDS)


# Resolved at import (NOT lazily): the atexit capture-stop runs during interpreter
# shutdown, when module globals like __file__ are already torn down -- computing it then
# raised NameError. Cache it now while __file__ is still live.
_REPO_DIST = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "dist"))


def _dist_dir():
    """Repo-root dist/ (gitignored) -- the build/byproduct drawer."""
    return _REPO_DIST


def _capture_dir():
    """dist/capture/ -- all live-capture artifacts namespaced under one dir (the
    rolling frame + the kill-switch flag), so dist/ stays tidy."""
    return os.path.join(_dist_dir(), "capture")


def _capture_frame_path(): return os.path.join(_capture_dir(), "latest.jpg")
def _capture_flag_path():  return os.path.join(_capture_dir(), "state.flag")


def _flag_write(state, by):
    """Atomically write the kill-switch flag. state is 'go' | 'stop'."""
    rec = {"state": state, "ts": round(time.time(), 3), "by": by}
    try:
        os.makedirs(_capture_dir(), exist_ok=True)
        tmp = _capture_flag_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec))
        os.replace(tmp, _capture_flag_path())
    except OSError:
        pass
    return rec


def _flag_read():
    try:
        with open(_capture_flag_path(), encoding="utf-8") as f:
            return json.loads(f.read() or "{}")
    except (OSError, ValueError):
        return None


def _list_video_devices():
    """Parsed avfoundation VIDEO inputs as [(index, name)]. Read-only enumeration."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "avfoundation",
             "-list_devices", "true", "-i", ""],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        text = out.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("can't list capture devices (is ffmpeg installed?): %s" % exc)
    devs, in_video = [], False
    for line in text.splitlines():
        low = line.lower()
        if "avfoundation video devices" in low:
            in_video = True;  continue
        if "avfoundation audio devices" in low:
            in_video = False; continue
        if in_video:
            m = re.search(r"\[(\d+)\]\s+(.*\S)", line)
            if m:
                devs.append((m.group(1), m.group(2).strip()))
    return devs


def _capture_candidates():
    """Ordered acceptable capture devices [(index, name)]. HARD PRIVACY RULE: the camera
    check applies to EVERY device -- reject any whose name says camera/built-in/mic. The
    NAME is the only guarantee; the index shifts between sessions and is never trusted.
    Prefer the configured card name, then ANY other non-camera video input as recovery.
    If nothing non-camera is left (e.g. every input is a camera) raise -- capture never
    falls back to a camera."""
    allow_screen = os.environ.get("CAPTURE_ALLOW_SCREEN", "") == "1"
    def ok(n):
        low = (n or "").lower()
        if _capture_name_forbidden(n):
            return False
        if not allow_screen and any(k in low for k in CAPTURE_SCREEN_KEYWORDS):
            return False            # screen-grab records the desktop, not the console feed
        return True
    safe = [(i, n) for (i, n) in _list_video_devices() if ok(n)]
    want = CAPTURE_DEVICE_NAME.lower()
    cands = ([(i, n) for (i, n) in safe if n.lower() == want] +
             [(i, n) for (i, n) in safe if n.lower() != want])
    if not cands:
        raise ValueError("No non-camera capture device present. Stopping to protect your privacy.")
    return cands


def _capture_terminate(proc):
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
    except Exception:
        pass


def _capture_clear(proc):
    with _capture_lock:
        if _capture_state.get("proc") is proc:
            _capture_state.update(proc=None, thread=None, stop=None, device=None, started=0.0)


def _capture_running():
    with _capture_lock:
        proc = _capture_state.get("proc")
    return bool(proc and proc.poll() is None)


def _capture_watchdog(proc, stop):
    """Poll the kill-switch flag every few seconds; stop ffmpeg when it dies on its
    own, when the flag says 'stop'/is missing, or when it has gone stale."""
    while not stop.wait(3.0):
        if proc.poll() is not None:                 # ffmpeg exited by itself
            _flag_write("stop", "ffmpeg-exit")
            _capture_clear(proc)
            return
        flag = _flag_read()
        ts = (flag or {}).get("ts", 0.0)
        stale = (time.time() - ts) > CAPTURE_STALE_SECS if ts else True
        if flag is None or flag.get("state") == "stop" or stale:
            _capture_terminate(proc)
            _flag_write("stop", "stale" if stale else "flag-stop")
            _capture_clear(proc)
            return


def _capture_try(name, frame):
    """Start ffmpeg on ONE non-camera device (BY NAME, never index -- a name matches
    atomically inside ffmpeg and can't slide onto the camera between enumerate and launch)
    and VERIFY it actually captures: the process must stay up AND write a FRESH frame within
    a short grace. On success leaves the live state + watchdog running and returns
    (True, ""); on failure terminates the process and returns (False, reason) so the caller
    can try the next device. Low-res by design (console video): 1280x720@10, don't tune."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-f", "avfoundation", "-video_size", "1280x720", "-framerate", "10",
           "-pixel_format", "uyvy422", "-i", name, "-update", "1", "-y", frame]
    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return False, "ffmpeg failed to start: %s" % exc
    captured = False
    deadline = t0 + 4.0   # a valid device opens + writes a frame in ~1-2s (avfoundation warm-up); a bad/busy one exits fast
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, "ffmpeg exited (rc=%s)" % proc.returncode
        try:
            if os.path.getmtime(frame) >= t0:
                captured = True
                break
        except OSError:
            pass
        time.sleep(0.2)
    if not captured:
        _capture_terminate(proc)
        return False, "no frame produced in time"
    stop = threading.Event()
    with _capture_lock:
        _capture_state.update(proc=proc, stop=stop, device=name, started=time.time())
    _flag_write("go", "pluto-start")
    th = threading.Thread(target=_capture_watchdog, args=(proc, stop), daemon=True)
    with _capture_lock:
        _capture_state["thread"] = th
    th.start()
    print("  [capture] started %s -> %s" % (name, frame))
    return True, ""


def _capture_start():
    """Start the persistent HDMI capture (idempotent). Tries each NON-camera device in
    turn (configured card first, then any other) and keeps the first that actually
    captures -- recover, don't error on the first miss. Returns (ok, info|error_str)."""
    if _capture_running():
        _flag_write("go", "go-refresh")
        with _capture_lock:
            return True, {"running": True, "device": _capture_state["device"], "reused": True}
    try:
        cands = _capture_candidates()
    except ValueError as exc:
        return False, str(exc)
    frame = _capture_frame_path()
    try:
        os.makedirs(_capture_dir(), exist_ok=True)
    except OSError:
        pass
    errors = []
    for idx, name in cands:
        ok, err = _capture_try(name, frame)
        if ok:
            return True, {"running": True, "device": name, "frame": frame}
        errors.append("%s[%s]: %s" % (name, idx, err))
    return False, "no working capture device (tried %d) -> %s" % (len(cands), " | ".join(errors))


def _capture_stop(reason="manual"):
    with _capture_lock:
        proc = _capture_state.get("proc")
        stop = _capture_state.get("stop")
    if stop:
        stop.set()
    if proc:
        _capture_terminate(proc)
        _capture_clear(proc)
        print("  [capture] stopped (%s)" % reason)
    _flag_write("stop", reason)


atexit.register(lambda: _capture_stop("shutdown"))


def _drive_libs():
    """Import the drive engine (generic controller + the dreame route->event adapter)
    from api/drive/. Imported lazily so the pynput/macOS dependency only loads when
    the drive is actually used (dev Mac), never at API startup on a headless box."""
    from drive import controller, dreame_events
    return controller, dreame_events


def _drive_stop():
    with _drive_lock:
        st = _drive_state
        stop, th, sink = st["stop"], st["thread"], st["sink"]
        st["stop"] = st["thread"] = st["sink"] = None
        st["live_target"] = None
    if stop:
        stop.set()
    if th:
        th.join(timeout=1.0)
    if sink:
        try:
            sink.release_all()
        except Exception:
            pass


def _drive_play(controller, events, mapping, sink, t0, speed):
    _drive_stop()
    stop = threading.Event()

    def run():
        try:
            controller.drive_from(events, mapping, sink, t0=t0, speed=speed,
                                  should_stop=stop.is_set)
        except Exception as exc:
            print("  [drive] %s" % exc)
        finally:
            try:
                sink.release_all()
            except Exception:
                pass

    def watchdog():
        # Stop the drive (releasing keys) if the frontend stops sending keepalives --
        # e.g. the browser/tab closed or crashed and no 'pause' reached us. Without
        # this the route keeps replaying and the character runs away (only an
        # emulator with background input visibly shows it).
        while not stop.wait(2.0):
            with _drive_lock:
                current = _drive_state.get("stop") is stop
                last = _drive_state.get("last_seen", 0.0)
            if not current:
                return                       # a newer drive took over
            if time.time() - last > DRIVE_TIMEOUT:
                _drive_stop()
                return

    th = threading.Thread(target=run, daemon=True)
    with _drive_lock:
        _drive_state.update(sink=sink, thread=th, stop=stop, last_seen=time.time())
    th.start()
    threading.Thread(target=watchdog, daemon=True).start()


# ── Request handler ──────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    config      = {}
    base_dir    = ""
    chat_config = {}
    node_roster = {}   # {name: cfg} discovered once at startup; the source of truth
    is_lab      = False  # this instance is the Lab (deploy engine present), not the C2
    lab_ip      = ""     # the Lab's address, when the C2 is told about it (LAB_IP)

    def log_message(self, format, *args):
        if "/deploy" in self.path or "/messages" in self.path:
            print("  [%s] %s" % (self.command, self.path))

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if _is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Pragma", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _identify(self):
        """Resolve the requester's chat identity: source IP -> known node, else
        User-Agent signature, else 'guest'. Server-authoritative."""
        mapping = ip_to_node(self.__class__.node_roster, self.__class__.config)
        ip = self.client_address[0]
        if ip in mapping:
            return mapping[ip]
        return node_for_ua(self.headers.get("User-Agent", "")) or "guest"

    def _known_device(self):
        """The named node bound to the requester's source IP, or None for a
        guest. This is the authoritative half of identity -- it can't be spoofed
        by a client-supplied name."""
        mapping = ip_to_node(self.__class__.node_roster, self.__class__.config,
                             self.__class__.is_lab, self.__class__.lab_ip)
        return mapping.get(self.client_address[0])

    def _handle_whoami(self):
        """Tell the client whether its IP is a named device. If so it posts as
        that device (locked); otherwise it's a guest and picks its own display
        string client-side (localStorage). No server-side guest registry."""
        self._send(200, {"node": self._known_device()})

    def _serve_retro(self):
        """Serve the barebones retro-console chat page with the client config +
        the requester's identity inlined (no fetch, no build step)."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            with open(os.path.join(script_dir, "retro.html"), "r") as f:
                html = f.read()
        except Exception:
            self._send(500, {"error": "retro.html missing"})
            return
        cfg  = self.__class__.chat_config or {}
        msgs = _get_messages(None)   # last 200 -- rendered once on load (light SSR)
        by_id, _ = _mention_index(self.__class__.node_roster, cfg)
        # The Wii page has no roster fetch / autocomplete, so we inline the full
        # reference and render it under the header: the flat tag list, and a per-node
        # command menu (handle + its verbs). Every verb is typeable even if not live
        # yet -- the server just replies out-of-office.
        handles = list(cfg.get("mentions", {}).get("base", [])) + \
                  sorted("@" + h for h in by_id.values())
        actions = [
            {"handle": "@" + by_id.get(nid, nid),
             "verbs":  [v.get("verb", "") for v in verbs]}
            for nid, verbs in cfg.get("nodeActions", {}).items()
        ]
        inlined = {
            "me":        self._identify(),
            "brand":     self.__class__.config.get("NODE_NAME", "CPC"),
            "primary":   self.__class__.config.get("UI_PRIMARY_COLOR", "") or "#1a1a1a",
            "secondary": self.__class__.config.get("UI_SECONDARY_COLOR", "") or "#888884",
            "handles":   handles,
            "actions":   actions,
            "messages":  msgs,
            "lastId":    msgs[-1]["id"] if msgs else 0,
        }
        blob = "<script>window.__CPC__ = %s;</script>" % json.dumps(inlined)
        body = html.replace("<!--CPC_CONFIG-->", blob).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def _dreame_repo(self):
        """Absolute path to the dreamehome-client repo (DREAME_CLIENT_PATH or default)."""
        cfg = self.__class__.config
        default = os.path.normpath(os.path.join(self.__class__.base_dir, "..", "..", "dreamehome-client"))
        return cfg.get("DREAME_CLIENT_PATH", "").strip() or default

    def _dreame_history(self, sync=False):
        routes = os.path.join(self._dreame_repo(), "routes.json")
        # On an explicit refresh (sync) with a live session, pull incrementally via
        # the lib -- only new cleans download a route -- and refresh the cache. A
        # plain load (or any failure) just reads the cached file.
        if sync and dreame_session.is_authenticated():
            try:
                live = dreame_session.sync_history(routes)
                if live is not None:
                    return live
            except Exception:
                pass
        if os.path.exists(routes):
            try:
                with open(routes, encoding="utf-8") as f:
                    return json.load(f).get("sessions", [])
            except Exception:
                return []
        return []

    def _serve_dreame(self):
        """Robutek tab state: live device state + history. History is the cached
        routes.json on a plain load; on ?sync=1 (the refresh button) it's re-pulled
        live via the logged-in client (incremental) and the cache is refreshed."""
        authed = dreame_session.is_authenticated()
        device = dreame_session.state() if authed else None
        error = None
        if authed and device is None:
            # session went stale / device unreachable
            authed = False
            error = "session expired -- please log in again"
        sync = urllib.parse.parse_qs(
            urllib.parse.urlparse(self.path).query).get("sync", ["0"])[0] == "1"
        self._send(200, {
            "authenticated": authed,
            "device":  device,
            "history": self._dreame_history(sync=sync),
            "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "error":   error,
        })

    def _handle_dreame_login(self):
        """POST /dreame/login {region, username, password | secondary_key}.
        Allowed from the local network (loopback + RFC-1918), not just the box
        itself -- on a trusted home LAN it's reasonable to sign in from a phone or
        another machine. Credentials are used once and never stored or logged.
        Caveat: the API is plain HTTP, so they cross the LAN in the clear.

        A host where the dreamehome client isn't importable (not installed and no
        checkout) can't log in, so it says so plainly instead of failing later."""
        if not dreame_session.available(self._dreame_repo()):
            self._send(503, {"authenticated": False,
                             "error": "the dreamehome client isn't installed on this host."})
            return
        if not _is_lan_ip(self.client_address[0]):
            self._send(403, {"authenticated": False,
                             "error": "login is allowed only from your local network"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return

        region   = str(body.get("region", "")).strip()
        username = str(body.get("username", "")).strip()
        password = body.get("password") or ""
        sec_key  = str(body.get("secondary_key", "")).strip()
        if not region:
            self._send(400, {"authenticated": False, "error": "region is required"})
            return

        ok, err = dreame_session.login(
            self._dreame_repo(), region=region,
            username=username or None, password=password or None,
            secondary_key=sec_key or None)
        if not ok:
            self._send(401, {"authenticated": False, "error": err or "login failed"})
            return
        self._send(200, {"authenticated": True, "device": dreame_session.state()})

    def _handle_dreame_logout(self):
        if not _is_lan_ip(self.client_address[0]):
            self._send(403, {"error": "only from your local network"})
            return
        dreame_session.logout()
        self._send(200, {"authenticated": False})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if parsed.path == "/retro":
            self._serve_retro()

        elif parsed.path == "/dreame":
            self._serve_dreame()

        elif parsed.path == "/nodes":
            self._send(200, self._build_nodes())

        elif parsed.path == "/connections":
            self._send(200, self._build_connections())

        elif parsed.path == "/whoami":
            self._handle_whoami()

        elif parsed.path == "/messages":
            qs    = urllib.parse.parse_qs(parsed.query)
            since = qs.get("since", [None])[0]
            try:
                since = int(since) if since is not None else None
            except ValueError:
                since = None
            self._send(200, _get_messages(since))

        elif len(parts) == 3 and parts[0] == "deploy" and parts[2] == "stream":
            self._handle_deploy_stream(parts[1])

        elif parts and parts[0] == "mappings":
            self._handle_mappings(parts)

        elif parsed.path == "/control/signal":
            self._handle_control_signal_get()

        elif parsed.path == "/control/capture":
            self._handle_capture_status()

        else:
            self._send(404, {"error": "not found"})

    def _handle_mappings(self, parts):
        """RESTful mapping store, organised by event-source dir -- the dir IS the
        filter (no query params, no DB). Mappings are reusable engine config:
          GET /mappings                   -> {source: [targets]}   (overview)
          GET /mappings/<source>          -> {"source":..., "targets":[...]}
          GET /mappings/<source>/<target> -> the mapping JSON
        """
        try:
            controller, _ = _drive_libs()
        except Exception:
            self._send(200, {} if len(parts) < 3 else {"error": "drive libs unavailable"})
            return
        if len(parts) == 1:
            self._send(200, {s: controller.list_targets(s) for s in controller.list_sources()})
        elif len(parts) == 2:
            self._send(200, {"source": parts[1], "targets": controller.list_targets(parts[1])})
        else:
            try:
                self._send(200, controller.load_mapping(parts[1], parts[2]))
            except Exception:
                self._send(404, {"error": "no mapping %s/%s" % (parts[1], parts[2])})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if parsed.path == "/messages":
            self._handle_post_message()
        elif parsed.path == "/dreame/login":
            self._handle_dreame_login()
        elif parsed.path == "/dreame/logout":
            self._handle_dreame_logout()
        elif parsed.path == "/robutek/drive":
            self._handle_drive()
        elif parsed.path == "/control/signal":
            self._handle_control_signal()
        elif parsed.path == "/control/capture":
            body = self._read_json_body()
            if body is not None:
                self._handle_capture(body)
        elif len(parts) == 2 and parts[0] == "workspace":
            self._handle_open(action=parts[0], target_node=parts[1])
        elif parsed.path == "/config/open":
            self._handle_open_config()
        elif len(parts) == 3 and parts[0] == "native":
            self._handle_native(parts[1], parts[2])
        else:
            self._send(404, {"error": "not found"})

    # ── Message handler ──────────────────────────────────────────────────────

    def _handle_post_message(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return

        # Identity rule: "you are a named device, or you are just a string."
        # A request from a known device IP is authoritatively that device and
        # cannot be spoofed. Everyone else is a guest -- we trust the client's
        # chosen display string (the SPA keeps it in localStorage), falling back
        # to a UA signature, then "guest". No server-side guest registry.
        device = self._known_device()
        if device:
            sender = device
        else:
            sender = (str(body.get("sender", "")).strip()
                      or node_for_ua(self.headers.get("User-Agent", ""))
                      or "guest")[:32]
        text = str(body.get("text", "")).strip()

        if not text:
            self._send(400, {"error": "text is required"})
            return

        msg = _new_message(sender, text)
        self._send(201, msg)

        # Generalised mention dispatch: EVERY node is taggable (@handle). Each
        # mentioned node responds per its kind -- claude converses, @l40 runs a
        # vacuum verb, and any other action-bearing node that isn't wired up yet
        # posts an out-of-office reply (claude's broke-mode gag, generalised).
        _, to_node = _mention_index(self.__class__.node_roster, self.__class__.chat_config)
        low = text.lower()
        for token, node_id in to_node.items():
            if token in low:
                self._dispatch_mention(node_id, sender, text)

    def _dispatch_mention(self, node_id, sender, text):
        """Route a tagged node. claude = conversational bot; dreame = vacuum verbs;
        any other node with declared nodeActions but no live handler = out-of-office."""
        if node_id == "claude":
            if _bot_enabled():
                threading.Thread(target=_bot_reply, args=(list(_messages),),
                                 daemon=True).start()
            return
        if node_id == "dreame":
            self._maybe_vacuum(sender, text)
            return
        actions = (self.__class__.chat_config or {}).get("nodeActions", {}).get(node_id)
        if not actions:
            return
        verbs  = [a.get("verb", "") for a in actions]
        tokens = text.lower().split()
        hit    = next((v for v in verbs if v and v in tokens), None)
        if hit:
            # A real command. This branch is the server-side hook where each handler
            # lives (modular: route (node_id, hit) into api/modules/<service>/). Built
            # ones run; the rest reply not-implemented -- the chat message IS the UX.
            if node_id == "substack" and hit == "post":
                # everything after the "@handle post" prefix is the content
                # (first line -> title, rest -> body); newlines preserved.
                rest = text.strip()
                first = rest.split(None, 1)
                if first and first[0].startswith("@"):       # drop a leading @mention
                    rest = first[1] if len(first) > 1 else ""
                vparts = rest.split(None, 1)
                content = vparts[1] if len(vparts) > 1 and vparts[0].lower() == hit else ""
                creds = self.__class__.node_roster.get("substack", {})
                threading.Thread(target=_substack_post, args=(creds, content), daemon=True).start()
                return
            _new_message(node_id, "'%s' is not implemented yet." % hit)
        else:
            # tagged with no command -> list what this node can do (discoverable,
            # mirrors @l40's verb hint -- a friendly defence against a bare mention)
            _new_message(node_id, "I can: %s. Tag me with one." % ", ".join(verbs))

    def _maybe_vacuum(self, sender, text):
        """Handle an @l40 chat command: run a verb, reply as the vacuum ('dreame').

        No sender gating: this is a LAN tool for a young project (the operator is
        a 'guest' too), status is read-only, and the control verbs aren't wired
        yet anyway. Reintroduce an allowlist if this ever leaves the local network.
        """
        verb = vacuum.parse_command(text)
        if not verb:
            _new_message("dreame", vacuum.VERB_HINT)
            return

        def work():
            # Route through the cloud session the Robutek tab holds (the L40 disables
            # its local API, so there's no local path). Read verbs ('status') work;
            # control verbs report that the cloud command endpoint isn't decoded yet.
            ok, msg = dreame_session.command(verb)
            print("  [vacuum] %s by %s -> %s (%s)" % (verb, sender, "ok" if ok else "fail", msg))
            _new_message("dreame", msg)

        threading.Thread(target=work, daemon=True).start()

    # ── Existing handlers (unchanged) ─────────────────────────────────────────

    def _handle_native(self, node_id, action):
        """A node's NATIVE-system action (e.g. the Wii's homebrew flash / game library),
        as opposed to its Linux side (SSH deploy / SMB). Not built yet -- we surface the
        capability in the drawer and let the API say so honestly, rather than hide it."""
        self._send(200, {"ok": False,
                         "error": "native '%s' for %s is not implemented yet" % (action, node_id)})

    def _handle_open(self, action, target_node):
        # CODE button — open WORKSPACE_PATH (the source checkout) in the IDE. This
        # runs on the API host, so it's host-local by nature: only meaningful when
        # Pluto runs on your workstation, not headless on the box. (SMB shares are
        # opened client-side in the browser, never here.)
        path = self.__class__.config.get("WORKSPACE_PATH", "").strip()
        if not path:
            self._send(400, {"error": "WORKSPACE_PATH not configured"})
            return
        path = os.path.expanduser(path)
        print("  [OPEN:%s] -> %s" % (action, path))
        open_path(path)
        self._send(200, {"status": "opened", "path": path, "target": target_node})

    def _handle_open_config(self):
        # Open a config dir on the API host — the dev-friendly way to edit config in your
        # own IDE instead of an in-drawer form. Lab-only by nature: the dir + a GUI live
        # on the workstation. Optional POST body {"sub": "mappings/dreame"} opens that
        # subdir (the Control rail's "open mapping dir"); no body opens config/ itself.
        # `sub` is path-traversal guarded to stay under config/.
        sub = ""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                sub = (json.loads(self.rfile.read(length)) or {}).get("sub", "") or ""
        except (ValueError, json.JSONDecodeError):
            sub = ""
        root = os.path.join(self.__class__.base_dir, "config")
        path = os.path.normpath(os.path.join(root, sub)) if sub else root
        if os.path.commonpath([root, path]) != root:   # refuse to escape config/
            self._send(400, {"error": "bad path"})
            return
        print("  [OPEN:config] -> %s" % path)
        open_path(path)
        self._send(200, {"status": "opened", "path": path})

    def _handle_press(self, body):
        """One-off controller button (the Enter->Start hotkey). Resolves key->button
        via the mapping's `controls`, then pulses it: through the live drive sink if a
        replay is running, else a transient connection to the selected target."""
        try:
            controller, _ = _drive_libs()
        except Exception as exc:
            self._send(200, {"ok": False, "error": "drive libs: %s" % exc})
            return
        try:
            mapping = controller.load_mapping(body.get("source") or "dreame",
                                              body.get("mapping") or "gamecube_dpad")
        except Exception as exc:
            self._send(200, {"ok": False, "error": "mapping: %s" % exc})
            return
        btn = body.get("btn") or (mapping.get("controls") or {}).get(body.get("key") or "")
        if not btn:
            self._send(200, {"ok": True, "ignored": body.get("key")})   # unbound key: no-op
            return
        ops = [{"op": "pulse", "btn": btn, "ms": int(body.get("ms") or 120)}]

        with _drive_lock:
            live = _drive_state.get("sink")
        if live is not None:                          # inject into the running replay
            try:
                live.apply(ops)
                self._send(200, {"ok": True, "pressed": btn, "via": "live"})
            except Exception as exc:
                self._send(200, {"ok": False, "error": "press: %s" % exc})
            return

        target = body.get("target")                   # no replay -> transient link
        try:
            if target == "pi":
                pi_cfg = self.__class__.node_roster.get("pi") or {}
                host = pi_cfg.get("HOST_IP", "").strip()
                port = pi_cfg.get("PI_BRIDGE_PORT", "").strip()
                if not host or not port:
                    self._send(200, {"ok": False, "error": "pi node has no HOST_IP/PI_BRIDGE_PORT"})
                    return
                sink = controller.NetworkSink(host, port, dev=body.get("dev"))
            elif target == "keyboard":
                sink = controller.KeyboardSink(button_keys=mapping.get("keys"))
            else:
                self._send(200, {"ok": False, "error": "unknown target: %s" % target})
                return
        except Exception as exc:
            self._send(200, {"ok": False, "error": "can't reach target (%s)" % exc})
            return
        try:
            sink.apply(ops)
        finally:
            try:
                sink.release_all()
            except Exception:
                pass
        self._send(200, {"ok": True, "pressed": btn, "via": "transient"})

    def _read_json_body(self):
        """Parse a JSON request body, or send 400 and return None."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length)) if length else {}
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return None

    def _handle_control_signal(self):
        """POST /control/signal {state:'wait'|'go', source, target, mapping}. Appends
        one JSONL line to the gitignored collaboration log (logs/control.log) that the
        chat-agreed 'Claude plays the console' flow tails: GO = play, WAIT = stop.
        GO also STARTS the HDMI capture (Claude can't -- Pluto owns that); WAIT only
        logs, it never stops the stream (the capture.flag kill-switch does)."""
        body = self._read_json_body()
        if body is None:
            return
        # Free-form on purpose: the client sends whatever -- the "go"/"wait"/"look" keys
        # from the buttons, or a free-text command from the input box ("left or right?").
        # Pluto just logs it; Claude (tailing the log) interprets. Only "go" has a side
        # effect (rolls capture). No per-message endpoint needed -- it's all this log.
        state = str(body.get("state", "")).strip()
        if not state:
            self._send(400, {"error": "empty message"})
            return
        rec = {"ts": round(time.time(), 3),
               "iso": datetime.now().isoformat(timespec="seconds"),
               "state": state,
               "source": str(body.get("source", "")) or None,
               "target": str(body.get("target", "")) or None,
               "mapping": str(body.get("mapping", "")) or None,
               "by": self._identify()}
        try:
            with open(_control_log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError as exc:
            self._send(200, {"ok": False, "error": "log write failed: %s" % exc})
            return
        print("  [control] %s (%s)" % (state[:60], rec["by"] or "?"))
        resp = {"ok": True, "state": state}
        if state == "go":                          # GO begins the session -> roll capture
            ok, info = _capture_start()
            resp["capture"] = info if ok else {"error": info}
        self._send(200, resp)

    def _handle_control_signal_get(self):
        """GET /control/signal -> the latest logged WAIT/GO record (or null). A cheap
        point-read of the collaboration log's tail."""
        last = None
        try:
            with open(_control_log_path(), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        except OSError:
            last = None
        rec = None
        if last:
            try:
                rec = json.loads(last)
            except ValueError:
                rec = None
        self._send(200, {"latest": rec})

    def _handle_capture(self, body):
        """POST /control/capture {action}. start (idempotent) | stop | keepalive.
        Pluto owns the capture lifecycle so Claude can't -- start is reachable only
        through Pluto (and is what GO triggers). Keepalive bumps the kill-switch flag
        so an open page keeps a running capture alive."""
        action = str(body.get("action", "")).strip()
        if action == "start":
            ok, info = _capture_start()
            if ok:
                resp = {"ok": True}
                resp.update(info)
                self._send(200, resp)
            else:
                self._send(200, {"ok": False, "error": info})
        elif action == "stop":
            _capture_stop("stop-button")
            self._send(200, {"ok": True, "running": False})
        elif action == "keepalive":
            running = _capture_running()
            flag = _flag_read()
            if running and flag and flag.get("state") == "go":
                _flag_write("go", "keepalive")     # don't resurrect a stopped capture
            self._send(200, {"ok": True, "running": running})
        else:
            self._send(400, {"error": "unknown capture action"})

    def _handle_capture_status(self):
        """GET /control/capture -> {running, device, started, flag, frame_mtime}."""
        with _capture_lock:
            proc = _capture_state.get("proc")
            info = {"running": bool(proc and proc.poll() is None),
                    "device": _capture_state.get("device"),
                    "started": _capture_state.get("started") or None}
        info["flag"] = _flag_read()
        try:
            info["frame_mtime"] = round(os.path.getmtime(_capture_frame_path()), 3)
        except OSError:
            info["frame_mtime"] = None
        self._send(200, info)

    def _make_sink(self, controller, target, mapping, dev=None):
        """Open a FRESH sink for `target` (pi -> NetworkSink to the hub; keyboard ->
        KeyboardSink for a local emulator). `dev` selects WHICH pico when the Pi runs
        more than one (the hub routes by it); None = the hub's default bridge. Raises
        ValueError(msg) on a bad or unreachable target so callers return a clean JSON error."""
        if target == "pi":
            pi_cfg = self.__class__.node_roster.get("pi") or {}
            host = pi_cfg.get("HOST_IP", "").strip()
            port = pi_cfg.get("PI_BRIDGE_PORT", "").strip()
            if not host or not port:
                raise ValueError("pi node has no HOST_IP/PI_BRIDGE_PORT in its .env")
            try:
                return controller.NetworkSink(host, port, dev=dev)
            except Exception as exc:
                raise ValueError("can't reach the Pi receiver at %s:%s (%s) -- is the "
                                 "hub up (run.sh serve / cpc-hub.service)?" % (host, port, exc))
        if target == "keyboard":
            try:
                return controller.KeyboardSink(button_keys=mapping.get("keys"))
            except Exception as exc:
                raise ValueError("keyboard sink: %s -- pip install pynput + grant the "
                                 "terminal Accessibility" % exc)
        raise ValueError("unknown target: %s" % target)

    def _live_ensure(self, controller, target, mapping, dev=None):
        """Ensure a PERSISTENT live-input sink for `target` is open (held across
        keydowns for true press-and-hold) with a watchdog that releases everything if
        the page goes quiet. Unlike a paced replay there's no drive thread -- just a
        held sink + watchdog reusing the single _drive_state slot (so it tears down any
        running replay first). Returns the sink; raises ValueError on a bad target."""
        with _drive_lock:
            sink = _drive_state.get("sink")
            if sink is not None and _drive_state.get("live_target") == target and _drive_state.get("live_dev") == dev:
                _drive_state["last_seen"] = time.time()
                return sink
        _drive_stop()                      # no sink, target changed, or pico changed: drop any prior drive
        sink = self._make_sink(controller, target, mapping, dev=dev)
        stop = threading.Event()

        def watchdog():
            while not stop.wait(2.0):
                with _drive_lock:
                    current = _drive_state.get("stop") is stop
                    last = _drive_state.get("last_seen", 0.0)
                if not current:
                    return                 # a newer drive/live-session took over
                if time.time() - last > DRIVE_TIMEOUT:
                    _drive_stop()
                    return

        with _drive_lock:
            _drive_state.update(sink=sink, thread=None, stop=stop,
                                last_seen=time.time(), live_target=target, live_dev=dev)
        threading.Thread(target=watchdog, daemon=True).start()
        return sink

    def _handle_hold(self, body):
        """POST /robutek/drive {action:'hold', down, btn|key, target, source, mapping}.
        Live press/release: down=true holds the button, down=false releases it. The
        button resolves from an explicit `btn` or a `key` via the mapping's `controls`.
        Keepalive (the page heartbeat) keeps the held sink alive between keystrokes."""
        try:
            controller, _ = _drive_libs()
        except Exception as exc:
            self._send(200, {"ok": False, "error": "drive libs: %s" % exc})
            return
        try:
            mapping = controller.load_mapping(body.get("source") or "keyboard",
                                              body.get("mapping") or "")
        except Exception as exc:
            self._send(200, {"ok": False, "error": "mapping: %s" % exc})
            return
        btn = body.get("btn") or (mapping.get("controls") or {}).get(body.get("key") or "")
        if not btn:
            self._send(200, {"ok": True, "ignored": body.get("key")})   # unbound key: no-op
            return
        try:
            sink = self._live_ensure(controller, body.get("target"), mapping, dev=body.get("dev"))
        except ValueError as exc:
            self._send(200, {"ok": False, "error": str(exc)})
            return
        op = "press" if body.get("down") else "release"
        try:
            sink.apply([{"op": op, "btn": btn}])
        except Exception as exc:
            self._send(200, {"ok": False, "error": "%s: %s" % (op, exc)})
            return
        self._send(200, {"ok": True, op: btn})

    def _handle_drive(self):
        """POST /robutek/drive {action, target, session, t, speed, mapping}.

        Drives the selected output from the Pluto playback clock. action 'play'
        (re)starts a paced replay from offset t at speed; 'pause'/'stop' release.
        Dev-only: returns {ok:false, error} (never 500) when the libs/sink/target
        aren't available, so the UI can surface it without breaking.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return

        action = body.get("action")
        if action in ("pause", "stop"):
            _drive_stop()
            self._send(200, {"ok": True})
            return
        if action == "keepalive":
            # heartbeat from the playing page; the watchdog stops the drive if these
            # go silent (browser closed/crashed before a 'pause' reached us). Also FORWARD
            # it to the live sink so the Pi-Hub doesn't idle-release a HELD input after ~6s
            # ("works a bit then stops" on press-and-hold). No-op on sinks without keepalive.
            with _drive_lock:
                _drive_state["last_seen"] = time.time()
                live = _drive_state.get("sink")
            if live is not None:
                try:
                    live.keepalive()
                except Exception:
                    pass
            self._send(200, {"ok": True})
            return
        if action == "press":
            # One-off button (the hidden Enter->Start hotkey). The key->button binding
            # lives in the mapping's `controls`; the route only steers, so this is how
            # you dismiss a console menu (e.g. the DC's VMU-removed prompt) by hand. Goes
            # through the LIVE drive if one's running, else a transient link to the target.
            self._handle_press(body)
            return
        if action == "hold":
            # Live press-and-HOLD for the keyboard/Claude sources: keydown holds the
            # button, keyup releases it, over a persistent sink so movement sustains.
            self._handle_hold(body)
            return
        if action != "play":
            self._send(400, {"error": "unknown action"})
            return

        target = body.get("target")
        if target not in ("keyboard", "pi"):
            self._send(200, {"ok": False, "error": "unknown target: %s" % target})
            return

        try:
            controller, dreame_events = _drive_libs()
        except Exception as exc:
            self._send(200, {"ok": False, "error": "drive libs unavailable: %s" % exc})
            return
        try:
            mapping = controller.load_mapping(body.get("source") or "dreame",
                                              body.get("mapping") or "gamecube_dpad")
        except Exception as exc:
            self._send(200, {"ok": False, "error": "mapping: %s" % exc})
            return
        speed = float(body.get("speed") or 1.0)
        if target == "pi":
            # Stream ops over TCP to the Pi-Hub op receiver (run.sh serve), which
            # frames them to the Pico. Host/port come from the discovered pi node.
            pi_cfg = self.__class__.node_roster.get("pi") or {}
            host = pi_cfg.get("HOST_IP", "").strip()
            port = pi_cfg.get("PI_BRIDGE_PORT", "").strip()
            if not host or not port:
                self._send(200, {"ok": False,
                    "error": "pi node has no HOST_IP/PI_BRIDGE_PORT in its .env"})
                return
            try:
                sink = controller.NetworkSink(host, port, dev=body.get("dev"))
            except Exception as exc:
                self._send(200, {"ok": False,
                    "error": "can't reach the Pi receiver at %s:%s (%s) -- is the hub up "
                             "(run.sh serve / cpc-hub.service)?" % (host, port, exc)})
                return
        else:
            # base movement duty (mapping) scaled by speed: 1x = robot pace, the speed
            # multipliers ramp toward a full sprint (capped at 1.0).
            eff_duty = min(1.0, float(mapping.get("move_duty", 1.0)) * max(speed, 1e-6))
            try:
                # the mapping carries its own per-emulator keys (its "keys" section)
                sink = controller.KeyboardSink(keyset="arrows", button_keys=mapping.get("keys"),
                                               move_duty=eff_duty)
            except Exception as exc:
                self._send(200, {"ok": False,
                    "error": "keyboard sink: %s -- pip install pynput, run the API under that "
                             "interpreter, and grant the terminal Accessibility." % exc})
                return

        session = body.get("session") or {}
        events = dreame_events.events_from_route(session)
        if not events:
            self._send(200, {"ok": False, "error": "no route in session"})
            return
        _drive_play(controller, events, mapping, sink,
                    float(body.get("t") or 0.0), float(body.get("speed") or 1.0))
        print("  [drive] play target=%s t=%.1f speed=%g events=%d" % (
            target, float(body.get("t") or 0.0), float(body.get("speed") or 1.0), len(events)))
        self._send(200, {"ok": True, "events": len(events), "target": target})

    def _handle_deploy_stream(self, node_id):
        """Stream deploy output as Server-Sent Events.

        Each output line is a default SSE message.
        ##STEP:<name> lines become 'step' events.
        A final 'done' event carries 'ok' or 'failed'.
        """
        base_dir = self.__class__.base_dir
        full_env = console_env_path(base_dir, node_id)
        if not os.path.exists(full_env):
            self._send(404, {"error": "no env file for %s" % node_id})
            return
        repo_root = os.path.dirname(base_dir)
        deploy_sh = os.path.join(repo_root, "deploy.sh")
        if not os.path.exists(deploy_sh):
            self._send(500, {"error": "deploy.sh not found"})
            return

        console_cfg = load_env(full_env)
        deploy_env  = os.environ.copy()
        for key in ("CUSTOM_SSH_ALIAS", "SSH_USER", "SSH_KEY_PATH"):
            val = console_cfg.get(key, "")
            if val:
                deploy_env[key] = val

        self.send_response(200)
        self.send_header("Content-Type",  "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors_headers()
        self.end_headers()

        def emit(event, data):
            try:
                msg = "event: %s\ndata: %s\n\n" % (event, data)
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        print("  [DEPLOY:stream] %s" % node_id)
        try:
            proc = subprocess.Popen(
                ["bash", deploy_sh, full_env],
                cwd=repo_root,
                env=deploy_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line.startswith("##STEP:"):
                    emit("step", line[7:])
                else:
                    emit("line", line)
            proc.wait()
            if proc.returncode == 0:
                emit("done", "ok")
            else:
                emit("done", "failed:%d" % proc.returncode)
        except Exception as e:
            emit("done", "failed:%s" % e)

    # ── Node / connection builders ────────────────────────────────────────────

    def _build_nodes(self):
        cfg      = self.__class__.config
        base_dir = self.__class__.base_dir
        nodes    = {}

        # Firmware tree (the deploy engine's checkout) -- present on the dev/Lab host,
        # absent on a deployed box. Used to DERIVE each Pico's pluto-vs-local deploy
        # ownership from whether its role has firmware. None => we can't tell.
        fw_root = os.path.join(os.path.dirname(base_dir), "pluto-pi-hub", "firmware")
        if not os.path.isdir(fw_root):
            fw_root = None

        # DEPLOY is only possible where the deploy ENGINE lives: the repo checkout
        # with deploy.sh at its root (the dev workstation). The deployed box ships
        # only /opt/cpc (api + dist + config -- no deploy.sh, no node .envs), so a
        # deploy there can't run. Gate every node's deploy flag on this one host-level
        # check -- deterministic, no build flag, same spirit as `code`/has_code.
        deploy_engine = os.path.isfile(os.path.join(os.path.dirname(base_dir), "deploy.sh"))

        # The roster was discovered once at startup (nodes/*/ + pluto the host); we
        # never rescan. Per request we only re-ping: collect every IP and probe them
        # in parallel, so down hosts time out once concurrently, not once per node.
        roster     = self.__class__.node_roster
        gateway_ip = cfg.get("GATEWAY_IP", "").strip()
        # LAB_IP (optional, pluto/.env): the workspace instance's address. When set,
        # the C2 can see + ping the Lab node (and offer a "Lab" jump). On the Lab
        # itself we don't ping it -- it's localhost, always up.
        lab_ip     = cfg.get("LAB_IP", "").strip()
        ips = [gateway_ip, lab_ip] + [c.get("HOST_IP", "").strip() for c in roster.values()]
        pinged = probe_many(ips)

        if gateway_ip:
            gw_up, _ = pinged.get(gateway_ip, (False, None))
            nodes["gateway"] = {
                "id":     "gateway",
                "name":   "Gateway",
                "ip":     gateway_ip,
                "color":  None,
                "status": "up" if gw_up else "down",
                "parent": "gateway",
                "smb":    None,
                "deploy": False,
                "folder": False,
                "os":     None,   # network gear — no OS badge
            }

        for node_id, console_cfg in roster.items():
            # Cloud connectors (nodes/cloud/*): off-network service buddies drawn as
            # the diagram's 'solar system'. Never pinged, and ALWAYS shown -- the dir
            # IS the declaration (CLAUDE.md). Identity (name/colour) comes from the
            # dir's .env or its .env.sample placeholder. `configured` (a real .env, vs
            # a bare .env.sample) is exposed as a sub-state for the UI, but never hides
            # the node -- prod ships .env.sample only (no secrets) yet must still draw
            # the whole cloud cluster.
            if console_cfg.get("_kind") == "cloud":
                nodes[node_id] = {
                    "id":         node_id,
                    "name":       console_cfg.get("NODE_NAME", node_id),
                    "ip":         "",
                    "color":      console_cfg.get("UI_PRIMARY_COLOR") or None,
                    "status":     "cloud",
                    "cloud":      True,
                    "configured": bool(console_cfg.get("_has_env")),
                    "smb":        None,
                    "deploy":     False,
                    "folder":     False,
                    "os":         None,
                }
                continue
            # A node configured without a HOST_IP (e.g. a placeholder loaded from
            # .env.sample) renders 'unconfigured' so "show unconfigured" reveals it.
            ip    = console_cfg.get("HOST_IP", "").strip()
            # The host node is the live command/comms instance -- label it "Pluto C2"
            # everywhere (bubble, drawer, deploy) so it reads apart from the Lab.
            name  = "Pluto C2" if node_id == "pluto" else console_cfg.get("NODE_NAME", node_id)
            color = console_cfg.get("UI_PRIMARY_COLOR") or None
            smb   = console_cfg.get("SMB_PATH", "").strip() or None
            alias    = console_cfg.get("CUSTOM_SSH_ALIAS", "").strip()
            ssh_user = console_cfg.get("SSH_USER", "").strip()
            ssh_key  = console_cfg.get("SSH_KEY_PATH", "").strip()
            deployable = deploy_engine and bool(ip and (alias or (ssh_user and ssh_key)))
            # CODE opens the source in the IDE on THIS host, so only surface it
            # where the checkout actually exists — true on the dev workstation,
            # false on the deployed headless box. Deterministic (no build flag).
            ws         = os.path.expanduser(console_cfg.get("WORKSPACE_PATH", "").strip())
            has_code   = bool(ws) and os.path.isdir(ws)
            up, det_os = pinged.get(ip, (False, None)) if ip else (False, None)
            status = ("up" if up else "down") if ip else "unconfigured"
            nodes[node_id] = {
                "id":     node_id,
                "name":   name,
                "ip":     ip,
                "color":  color,
                "status": status,
                "smb":    smb,
                "deploy": deployable,
                "folder": bool(smb),
                "code":   has_code,
                # Precedence: .env OS= override > known-by-definition > probe TTL.
                # (e.g. OS=native on a Wii homebrew build to drop the Tux.)
                "os":     _detect_os(console_cfg, KNOWN_OS.get(node_id) or det_os),
                # Declared Pico fleet (PICO_<chipid>=... lines); [] for nodes without.
                # deploy ownership is derived against the firmware tree (fw_root).
                "picos":  picos_from_env(console_cfg, fw_root),
            }

        # The Lab node -- Pluto's workspace instance (this repo checkout: the bench
        # that builds, deploys and opens code). Config-gated like every other node:
        # the Lab always sees itself (deploy_engine present -> 'up', it's localhost);
        # the C2 sees it only when pluto/.env declares LAB_IP, then pings it like a
        # LAN host (offline workstation -> 'down'). No LAB_IP on the C2 -> no Lab.
        if deploy_engine or lab_ip:
            if deploy_engine:
                # The Lab IS this machine -- read its real OS for the bubble badge.
                lab_status = "up"
                lab_os = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system())
            else:
                lab_up, lab_det = pinged.get(lab_ip, (False, None))
                lab_status = "up" if lab_up else "down"
                lab_os = lab_det   # best-effort guess from the ping TTL
            nodes["lab"] = {
                "id":     "lab",
                "name":   "Pluto Lab",
                # '' on the Lab itself (it's localhost -- the frontend falls back to
                # the current host); the real LAB_IP when the C2 is looking at it.
                "ip":     "" if deploy_engine else lab_ip,
                "color":  cfg.get("UI_PRIMARY_COLOR") or None,
                "status": lab_status,
                "smb":    None,
                "deploy": False,
                "folder": False,
                "code":   False,
                "os":     lab_os,
                "lab":    True,
            }

        # The 'cloud' hub is virtual -- like 'gateway' it has no config dir. Cloud
        # connectors are always shown, so draw the hub whenever >=1 of them exists.
        if any(n.get("cloud") for n in nodes.values()):
            nodes["cloud"] = {
                "id": "cloud", "name": "Cloud", "ip": "", "color": None,
                "status": "cloud",
                "cloud": True, "smb": None, "deploy": False, "folder": False, "os": None,
            }

        return nodes

    def _build_connections(self):
        base_dir = self.__class__.base_dir
        connections_path = os.path.join(base_dir, "config", "connections.json")
        if not os.path.exists(connections_path):
            return []
        with open(connections_path) as f:
            return json.load(f)


# ── Startup ──────────────────────────────────────────────────────────────────

def run():
    global _log_path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    env_path   = os.path.join(parent_dir, ".env")

    if not os.path.exists(env_path):
        print("\n  ERROR: .env not found at: %s" % env_path)
        print("  Copy .env.sample to .env and fill in the values.\n")
        sys.exit(1)

    config = load_env(env_path)

    missing_keys = [v for v in REQUIRED_VARS if not config.get(v, "").strip()]
    if missing_keys:
        print("\n  ERROR: missing required config values in %s:" % env_path)
        for k in missing_keys:
            print("    %s=" % k)
        print()
        sys.exit(1)

    # Optional log file — stored alongside the env
    _log_path = os.path.join(parent_dir, "messages.log")
    # Rehydrate the recent feed from the log so a restart/deploy doesn't wipe chat.
    _load_recent_messages()
    if _messages:
        print("  chat: restored %d recent message(s) from the log" % len(_messages))

    # Shared client-side chat config (commands, mention tokens) — one source of
    # truth in config/, also imported by the Vue app; inlined into the /retro page.
    # Lives at config/chat.json in both the repo and the deploy (deploy ships config/).
    chat_path = os.path.join(parent_dir, "config", "chat.json")
    try:
        with open(chat_path) as f:
            Handler.chat_config = json.load(f)
        print("  chat.json: %d nodes with actions" % len(Handler.chat_config.get("nodeActions", {})))
    except Exception as exc:
        print("  chat.json: not loaded (%s)" % exc)

    global _bot_key, _bot_model, _bot_broke
    _bot_key = config.get("ANTHROPIC_API_KEY", "").strip() or None
    _bot_model = config.get("ANTHROPIC_MODEL", "").strip() or _bot_model
    _bot_broke = (not _bot_key) and \
        config.get("CLAUDE_BROKE_MODE", "").strip().lower() in ("1", "true", "yes", "on")
    if _bot_key:
        print("  @claude bot: enabled (%s)" % _bot_model)
    elif _bot_broke:
        print("  @claude bot: BROKE MODE (no key, no cost -- always broke, for laughs)")
    else:
        print("  @claude bot: disabled (set ANTHROPIC_API_KEY, or CLAUDE_BROKE_MODE=1 for the gag)")

    Handler.config   = config
    Handler.base_dir = parent_dir
    # Instance identity (deterministic, no build flag): the Lab is the host that holds
    # the deploy engine (deploy.sh at the repo root); the C2 is the deployed box.
    Handler.is_lab = os.path.isfile(os.path.join(os.path.dirname(parent_dir), "deploy.sh"))
    Handler.lab_ip = config.get("LAB_IP", "").strip()
    print("  instance: %s%s" % ("Lab" if Handler.is_lab else "C2",
                                 ("  (lab @ %s)" % Handler.lab_ip) if Handler.lab_ip else ""))

    # Discover the node roster ONCE: nodes/local + nodes/cloud dirs + pluto (the host).
    roster = discover_nodes(parent_dir)
    roster["pluto"] = config
    Handler.node_roster = roster
    n_cloud = sum(1 for c in roster.values() if c.get("_kind") == "cloud")
    print("  nodes: %d discovered (%d local + %d cloud): %s" % (
        len(roster), len(roster) - n_cloud, n_cloud, ", ".join(sorted(roster))))

    # Drive mappings live in config/mappings (shipped as part of config/). Point the
    # the controller there unless the env already set CPC_MAPPINGS.
    os.environ.setdefault("CPC_MAPPINGS", os.path.join(parent_dir, "config", "mappings"))

    host_ip = config.get("HOST_IP", "").strip()

    class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True
        daemon_threads      = True

    server = _Server(("0.0.0.0", PORT), Handler)

    # Release any held synthetic keys on shutdown, so a kill/restart mid-drive can't
    # strand a keydown -- an emulator's background input would hold it forever and
    # the character keeps walking. atexit covers normal exit + Ctrl-C; the SIGTERM
    # handler covers `kill` (e.g. start-pluto-lab.sh restarting the API).
    atexit.register(_drive_stop)

    def _on_term(_sig, _frame):
        _drive_stop()
        os._exit(0)

    signal.signal(signal.SIGTERM, _on_term)

    print("  api listening on 0.0.0.0:%d" % PORT)
    if host_ip:
        print("  LAN: http://%s:%d" % (host_ip, PORT))
    print("  logs: %s" % _log_path)
    print("  ctrl-c to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopping...")
        _drive_stop()
        server.server_close()


if __name__ == "__main__":
    run()
