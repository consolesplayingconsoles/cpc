"""
vacuum.py — optional Dreame L40 control for the @l40 chat command.

Talks to the vacuum over the local miio protocol using the token from
dreame/.env (which lives on the Pluto host and is never deployed to consoles).

python-miio is an OPTIONAL dependency. If it is not installed on the Pluto host,
vacuum commands return a clear message instead of crashing the API. To enable:
    pip install python-miio==0.5.12      (same version batocera uses)

Only a small, SAFE verb set is exposed (locate / clean / dock / stop) — no
settings, firmware, or anything destructive — because the trigger is a shared
chat surface. Architecturally the master console (batocera) owns the vacuum;
Pluto drives it directly here only because it is the chat hub and already reads
the console env files. Replies are ASCII-only so the console TUIs can render them.
"""
import re

# canonical verb -> (miio method names tried in order, ASCII confirmation line)
_VERBS = {
    "locate": (("locate", "find", "identify", "find_robot"), "beep beep -- over here."),
    "clean":  (("start", "start_clean"),                      "rolling out. cleaning started."),
    "dock":   (("home", "return_home"),                       "heading home to charge."),
    "stop":   (("stop", "pause"),                             "stopping. parked in place."),
}

# keyword -> canonical verb (first match in the message wins)
_KEYWORDS = {
    "locate": "locate", "find": "locate", "where": "locate", "ping": "locate",
    "clean": "clean", "start": "clean", "go": "clean", "vacuum": "clean", "mop": "clean",
    "dock": "dock", "home": "dock", "charge": "dock", "back": "dock", "return": "dock",
    "stop": "stop", "halt": "stop", "pause": "stop",
}

VERB_HINT = "try: @l40 locate | clean | dock | stop"


def parse_command(text):
    """Return a canonical verb if the message names one, else None."""
    for tok in re.findall(r"[a-z]+", text.lower()):
        if tok in _KEYWORDS:
            return _KEYWORDS[tok]
    return None


def run(verb, ip, token):
    """Execute a safe verb on the vacuum. Returns (ok: bool, message: str).

    NOTE: by the operator's standing instruction this is never invoked against
    the real hardware during development; the dispatch logic is unit-tested with
    a mocked miio device. The message is ASCII-only for console terminals.
    """
    spec = _VERBS.get(verb)
    if not spec:
        return False, "unknown vacuum command: %s" % verb
    methods, confirm = spec

    try:
        from miio import DreameVacuum
    except ImportError:
        return False, "vacuum control not installed (pip install python-miio on pluto)."

    try:
        vac = DreameVacuum(ip=ip, token=token)
        fn  = next((getattr(vac, m) for m in methods if hasattr(vac, m)), None)
        if fn is None:
            return False, "vacuum lib (this version) exposes none of: %s" % ", ".join(methods)
        fn()
        return True, confirm
    except Exception as exc:
        return False, "couldn't reach the vacuum: %s" % exc
