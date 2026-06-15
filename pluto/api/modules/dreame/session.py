"""In-memory DreameHome session for the Pluto API.

Holds ONE logged-in dreamehome.Client in process memory. The threaded HTTP
server shares it under a lock. Credentials are used once to log in and then
discarded -- only the resulting session (its refresh token, in RAM) remains.
NOTHING is written to disk; on API restart you log in again (the browser's
password manager autofills, so it's one click).

`dreamehome` is pure stdlib, so it imports fine under Pluto's plain python3 once
the dreamehome-client repo is on sys.path.
"""
import sys
import os
import json
import threading
from datetime import datetime

_lock = threading.RLock()
_client = None
_dh = None              # the imported dreamehome module (lazy)
_import_error = None


def _ensure_import(repo_path=None):
    """Import the dreamehome client. Cached. Returns the module or None.

    Prefer it as a normally installed package (pip install / on PYTHONPATH); only
    if that fails do we fall back to a repo checkout on sys.path (DREAME_CLIENT_PATH).
    So once the lib is installed -- or published -- no path config is needed."""
    global _dh, _import_error
    if _dh is not None:
        return _dh
    try:                       # installed package (the normal, no-config path)
        import dreamehome
        _dh = dreamehome
        _import_error = None
        return _dh
    except ImportError:
        pass
    if repo_path:              # dev fallback: an uninstalled checkout on disk
        try:
            if repo_path not in sys.path:
                sys.path.insert(0, repo_path)
            import dreamehome
            _dh = dreamehome
            _import_error = None
            return _dh
        except Exception as exc:
            _import_error = "could not import dreamehome from %r: %s" % (repo_path, exc)
            return None
    _import_error = ("the dreamehome client isn't installed -- pip install it, or "
                     "set DREAME_CLIENT_PATH to a local checkout.")
    return None


def available(repo_path=None):
    """True if the dreamehome client can be imported (installed, or via repo_path)."""
    return _ensure_import(repo_path) is not None


def is_authenticated():
    with _lock:
        return _client is not None


def login(repo_path, region, username=None, password=None, secondary_key=None):
    """Log in and hold the session in memory. Returns (ok, error_or_None).

    Credentials are not retained beyond the login call."""
    global _client
    dh = _ensure_import(repo_path)
    if dh is None:
        return False, _import_error
    try:
        auth = dh.StaticAuth(region=region, username=username,
                             password=password, secondary_key=secondary_key)
        client = dh.Client.login(auth=auth)
        client.use_primary_device()   # validate the session + load the device
    except Exception as exc:
        return False, str(exc)
    with _lock:
        _client = client
    return True, None


def logout():
    global _client
    with _lock:
        _client = None


# Friendly status labels. This is the single source of truth shared by BOTH the
# Robutek tab (it renders the `status_human` field below) and the @l40 chat status
# reply, so they can never drift. Mirrors the raw status_label enum from the
# dreamehome lib; unknown labels fall back to a generic prettify.
_STATUS_HUMAN = {
    "SWEEPING": "Sweeping", "IDLE": "Idle", "PAUSED": "Paused", "ERROR": "Error",
    "RETURNING": "Returning", "CHARGING": "Charging", "MOPPING": "Mopping",
    "DRYING": "Drying", "WASHING": "Washing", "RETURNING_WASHING": "Returning to wash",
    "BUILDING_MAP": "Building map", "SWEEPING_AND_MOPPING": "Sweep + mop",
    "CHARGING_COMPLETED": "Charged", "UPGRADING": "Updating", "UNKNOWN": "Unknown",
}


def human_status(label):
    """A friendly status string for a raw status_label enum (e.g.
    CHARGING_COMPLETED -> 'Charged'). Generic prettify for anything unmapped."""
    if not label:
        return "Unknown"
    return _STATUS_HUMAN.get(label) or label.replace("_", " ").capitalize()


def state():
    """{name, model, firmware, activity, ...} or None if not authed / unreachable."""
    with _lock:
        client = _client
    if client is None:
        return None
    try:
        dev = client.device           # cached after use_primary_device()
        st = client.live_state()
    except Exception:
        return None
    return {
        "name": dev.get("customName"),
        "model": dev.get("model"),
        "firmware": st.get("firmware"),
        "activity": st.get("activity"),
        "status_label": st.get("status_label"),
        "status_human": human_status(st.get("status_label")),
        "status_int": st.get("status_int"),
        "battery": st.get("battery"),
        "online": st.get("online"),
    }


def sync_history(out_path):
    """Pull cleaning history via the logged-in client and refresh the on-disk
    cache at out_path. INCREMENTAL: only NEW sessions download/decode a route
    (cached ones keep theirs), so a routine refresh is one event-list call plus a
    download for each new clean. Returns the session list (newest first), or None
    if not authenticated or the pull fails -- the caller falls back to the cache.
    Mirrors dreamehome.commands.routes_main, but reuses our in-memory client."""
    with _lock:
        client = _client
    if client is None:
        return None
    existing, meta = {}, {}
    try:
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f)
            for s in old.get("sessions", []):
                sid = str(s.get("session_id", ""))
                if sid:
                    existing[sid] = s
            meta = {k: v for k, v in old.items() if k != "sessions"}
    except Exception:
        existing, meta = {}, {}
    try:
        merged, _new = client.sync_cleaning(existing=existing)
    except Exception:
        return None   # network/session failure -> caller uses the cached file
    sessions = sorted(merged.values(),
                      key=lambda s: s.get("start_ts") or s.get("date") or "",
                      reverse=True)
    try:   # write back the cache (best-effort; a failed write just means next
        payload = dict(meta)        # refresh re-pulls)
        payload["sessions"] = sessions
        payload["exported"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass
    return sessions


# read-only chat verbs the cloud session can answer without commanding the robot
_READ_VERBS = {"status"}


def command(verb):
    """Run an @l40 chat verb against the cloud session. Returns (ok, message).

    READ verbs ('status') report live state via the same cloud read the Robutek
    tab already uses -- no command is sent to the robot. CONTROL verbs (locate/
    clean/dock/stop) are NOT wired: the cloud command endpoint was never reverse-
    engineered (only the read APIs are), so they return a clear note instead of
    firing a guessed request at a physical robot."""
    if verb in _READ_VERBS:
        st = state()
        if st is None:
            return False, "not signed into Dreamehome. Open the Dreame tab and sign in first."
        # same friendly label the Robutek tab shows (via status_human)
        act = st.get("status_human") or st.get("activity") or "Unknown"
        bat = st.get("battery")
        batstr = ("%d%%" % bat) if isinstance(bat, (int, float)) else "?"
        net = "online" if st.get("online") else "offline"
        return True, "status: %s, battery %s, %s." % (act, batstr, net)
    return False, ("i can read the vacuum (try '@l40 status'), but sending commands "
                   "isn't wired yet: the cloud control endpoint isn't decoded, only "
                   "the read apis are.")
