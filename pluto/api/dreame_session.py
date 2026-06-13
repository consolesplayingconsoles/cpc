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


def _ensure_import(repo_path):
    """Import dreamehome (adding the repo to sys.path). Cached. Returns the
    module or None (with _import_error set)."""
    global _dh, _import_error
    if _dh is not None:
        return _dh
    try:
        if repo_path and repo_path not in sys.path:
            sys.path.insert(0, repo_path)
        import dreamehome
        _dh = dreamehome
        _import_error = None
    except Exception as exc:
        _import_error = "could not import dreamehome from %r: %s" % (repo_path, exc)
    return _dh


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
