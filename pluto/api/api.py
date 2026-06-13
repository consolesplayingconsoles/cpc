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

import vacuum
import dreame_session


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

# Chat senders allowed to drive the @l40 vacuum (a shared chat surface controls a
# physical robot, so default to the operator's own surfaces). Overridable via env.
_vacuum_senders = {"pluto", "host"}

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


REQUIRED_VARS = ["GATEWAY_IP"]

NODE_IDS = ["wii", "dc", "ps3", "gba", "ws", "batocera", "dreame", "birdbuddy", "pi", "pluto", "vmu"]

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


# ── Shared helpers ───────────────────────────────────────────────────────────

def console_env_path(base_dir, node_id):
    """Path to a console's env file. Prefer the real .env; fall back to the
    committed .env.sample so a node that has a blueprint but no .env yet still
    surfaces on the map as 'unconfigured' (empty HOST_IP) instead of vanishing
    — e.g. a device staged ahead of the hardware arriving."""
    real = os.path.normpath(os.path.join(base_dir, "..", node_id, ".env"))
    if os.path.exists(real):
        return real
    return os.path.normpath(os.path.join(base_dir, "..", node_id, ".env.sample"))


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


def ip_to_node(base_dir, config):
    """Build {ip: node_id}. Localhost + pluto's own HOST_IP map to 'pluto' so
    the operator can QA the client from the Mac."""
    mapping = {"127.0.0.1": "pluto", "::1": "pluto"}
    host_ip = config.get("HOST_IP", "").strip()
    if host_ip:
        mapping[host_ip] = "pluto"
    for node_id in NODE_IDS:
        env = load_env(console_env_path(base_dir, node_id))
        ip  = env.get("HOST_IP", "").strip()
        if ip:
            mapping[ip] = node_id
    return mapping


def node_for_ua(ua):
    low = (ua or "").lower()
    for sig, node in _UA_NODE_SIGNATURES:
        if sig in low:
            return node
    return None


# ── Robutek drive: dev-only vacuum-replay -> emulator/console output ──────────
# The Pluto playback clock drives a controller Sink via cpc_python_core. Lazy
# everything: cpc-python-client isn't on the deployed headless box, and the one
# working sink (KeyboardSink) needs pynput + macOS Accessibility -- so this whole
# feature degrades to a clean JSON error anywhere but the dev Mac.
_drive_lock  = threading.Lock()
_drive_state = {"sink": None, "thread": None, "stop": None}


def _drive_libs(base_dir):
    """Import the bridge libs from the sibling cpc-python-client (dev checkout)."""
    repo_root = os.path.dirname(base_dir)
    cpc = os.path.join(repo_root, "cpc-python-client")
    if cpc not in sys.path:
        sys.path.insert(0, cpc)
    from cpc_python_core import controller
    from cpc_python_core.bridges import dreame_events
    return controller, dreame_events


def _drive_stop():
    with _drive_lock:
        st = _drive_state
        stop, th, sink = st["stop"], st["thread"], st["sink"]
        st["stop"] = st["thread"] = st["sink"] = None
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

    th = threading.Thread(target=run, daemon=True)
    with _drive_lock:
        _drive_state.update(sink=sink, thread=th, stop=stop)
    th.start()


# ── Request handler ──────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    config      = {}
    base_dir    = ""
    chat_config = {}

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
        mapping = ip_to_node(self.__class__.base_dir, self.__class__.config)
        ip = self.client_address[0]
        if ip in mapping:
            return mapping[ip]
        return node_for_ua(self.headers.get("User-Agent", "")) or "guest"

    def _known_device(self):
        """The named node bound to the requester's source IP, or None for a
        guest. This is the authoritative half of identity -- it can't be spoofed
        by a client-supplied name."""
        mapping = ip_to_node(self.__class__.base_dir, self.__class__.config)
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
        inlined = {
            "me":       self._identify(),
            "brand":    self.__class__.config.get("NODE_NAME", "CPC"),
            "primary":   self.__class__.config.get("UI_PRIMARY_COLOR", "") or "#1a1a1a",
            "secondary": self.__class__.config.get("UI_SECONDARY_COLOR", "") or "#888884",
            "commands":  cfg.get("commands", []),
            "mentions":  cfg.get("mentions", {}),
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

    def _is_loopback(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

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
        Loopback-only. Credentials are used once and never stored or logged."""
        if not self._is_loopback():
            self._send(403, {"error": "login is only allowed from the local machine"})
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
        if not self._is_loopback():
            self._send(403, {"error": "only from the local machine"})
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

        elif parsed.path == "/robutek/mappings":
            self._handle_mappings()

        else:
            self._send(404, {"error": "not found"})

    def _handle_mappings(self):
        """List available mapping stems from the root mappings store (dev-only)."""
        try:
            controller, _ = _drive_libs(self.__class__.base_dir)
            self._send(200, {"mappings": controller.list_mappings()})
        except Exception:
            self._send(200, {"mappings": []})

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
        elif len(parts) == 2 and parts[0] == "workspace":
            self._handle_open(action=parts[0], target_node=parts[1])
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

        if _bot_enabled() and "@claude" in text.lower():
            t = threading.Thread(
                target=_bot_reply,
                args=(list(_messages),),
                daemon=True,
            )
            t.start()

        low = text.lower()
        if "@l40" in low or "@dreame" in low:
            self._maybe_vacuum(sender, text)

    def _maybe_vacuum(self, sender, text):
        """Handle an @l40 chat command: run a safe verb, reply as the vacuum.

        Gated to an allowlist of senders because the chat is a shared surface
        and the target is a physical robot. The vacuum 'replies' as 'dreame'.
        """
        verb = vacuum.parse_command(text)
        if not verb:
            _new_message("dreame", vacuum.VERB_HINT)
            return
        if sender.lower() not in _vacuum_senders:
            _new_message("dreame", "nice try -- '%s' is not on the vacuum allowlist." % sender)
            return

        env_path = console_env_path(self.__class__.base_dir, "dreame")
        env      = load_env(env_path)
        ip       = env.get("HOST_IP", "").strip()
        token    = env.get("TOKEN", "").strip()
        if not ip or not token:
            _new_message("dreame", "vacuum not configured (HOST_IP/TOKEN missing in dreame/.env).")
            return

        def work():
            ok, msg = vacuum.run(verb, ip, token)
            print("  [vacuum] %s -> %s (%s)" % (verb, "ok" if ok else "fail", msg))
            _new_message("dreame", msg)

        threading.Thread(target=work, daemon=True).start()

    # ── Existing handlers (unchanged) ─────────────────────────────────────────

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
        if action != "play":
            self._send(400, {"error": "unknown action"})
            return

        target = body.get("target")
        if target == "pi":
            self._send(200, {"ok": False,
                "error": "Console (Raspberry Pi) output isn't wired yet (Pico pending)."})
            return
        if target != "keyboard":
            self._send(200, {"ok": False, "error": "unknown target: %s" % target})
            return

        try:
            controller, dreame_events = _drive_libs(self.__class__.base_dir)
        except Exception as exc:
            self._send(200, {"ok": False, "error": "drive libs unavailable: %s" % exc})
            return
        try:
            mapping = controller.load_mapping(body.get("mapping") or "dreame-to-gamecube")
        except Exception as exc:
            self._send(200, {"ok": False, "error": "mapping: %s" % exc})
            return
        speed = float(body.get("speed") or 1.0)
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

        # Pluto itself is just another discovered node: it carries a real HOST_IP
        # (the box the dashboard is deployed to) and is pinged like everything
        # else — no phantom localhost entry. It's built by the NODE_IDS loop below
        # from pluto/.env, which adds its CODE/DEPLOY/FILES buttons.

        gateway_ip = cfg.get("GATEWAY_IP", "").strip()
        if gateway_ip:
            gw_up, _ = probe(gateway_ip)
            nodes["gateway"] = {
                "id":     "gateway",
                "name":   "gateway",
                "ip":     gateway_ip,
                "color":  None,
                "status": "up" if gw_up else "down",
                "parent": "gateway",
                "smb":    None,
                "deploy": False,
                "folder": False,
                "os":     None,   # network gear — no OS badge
            }

        for node_id in NODE_IDS:
            full_path = console_env_path(base_dir, node_id)
            if not os.path.exists(full_path):
                continue
            console_cfg = load_env(full_path)
            ip    = console_cfg.get("HOST_IP", "").strip()
            name  = console_cfg.get("NODE_NAME", node_id)
            color = console_cfg.get("UI_PRIMARY_COLOR") or None
            smb   = console_cfg.get("SMB_PATH", "").strip() or None
            alias    = console_cfg.get("CUSTOM_SSH_ALIAS", "").strip()
            ssh_user = console_cfg.get("SSH_USER", "").strip()
            ssh_key  = console_cfg.get("SSH_KEY_PATH", "").strip()
            deployable = bool(ip and (alias or (ssh_user and ssh_key)))
            # CODE opens the source in the IDE on THIS host, so only surface it
            # where the checkout actually exists — true on the dev workstation,
            # false on the deployed headless box. Deterministic (no build flag).
            ws         = os.path.expanduser(console_cfg.get("WORKSPACE_PATH", "").strip())
            has_code   = bool(ws) and os.path.isdir(ws)
            up, det_os = probe(ip) if ip else (False, None)
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
            }

        if _bot_enabled():
            nodes[BOT_ID] = {
                "id":     BOT_ID,
                "name":   "Claude",
                "ip":     "",
                "color":  "#d97757",
                "status": "up" if _bot_online() else "down",
                "smb":    None,
                "deploy": False,
                "folder": False,
            }

        return nodes

    def _build_connections(self):
        base_dir = self.__class__.base_dir
        connections_path = os.path.join(base_dir, "connections.json")
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

    # Shared client-side chat config (commands, mention tokens) — one source of
    # truth, also imported by the Vue app; inlined into the /retro page.
    # Dev runs from the repo (src/chat.json); a deploy flattens it to the root so
    # the box never needs the whole src/ tree shipped — just dist/ + this file.
    chat_path = os.path.join(parent_dir, "chat.json")
    if not os.path.exists(chat_path):
        chat_path = os.path.join(parent_dir, "src", "chat.json")
    try:
        with open(chat_path) as f:
            Handler.chat_config = json.load(f)
        print("  chat.json: %d commands" % len(Handler.chat_config.get("commands", [])))
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

    global _vacuum_senders
    senders = config.get("VACUUM_SENDERS", "").strip()
    if senders:
        _vacuum_senders = {s.strip().lower() for s in senders.split(",") if s.strip()}
    print("  @l40 vacuum: senders allowed -> %s" % ", ".join(sorted(_vacuum_senders)))

    Handler.config   = config
    Handler.base_dir = parent_dir

    host_ip = config.get("HOST_IP", "").strip()

    class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True
        daemon_threads      = True

    server = _Server(("0.0.0.0", PORT), Handler)

    # Release any held synthetic keys on shutdown, so a kill/restart mid-drive can't
    # strand a keydown -- Dolphin's background input would hold it forever and the
    # character keeps walking. atexit covers normal exit + Ctrl-C; the SIGTERM
    # handler covers `kill` (e.g. start-pluto.sh restarting the API).
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
