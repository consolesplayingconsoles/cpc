"""
core/chat.py — Pluto group chat API client.

Pure stdlib, Python 3.6+. No C extensions.
"""
import json
import re
import subprocess
import time
import threading

try:
    from urllib.request import urlopen, Request
except ImportError:
    pass  # Python 2 guard

TIMEOUT_HTTP = 5     # seconds for API calls
TIMEOUT_SHELL = 300  # 5 min — long scripts are fine; Ctrl+C cancels early
STDOUT_CAP    = 500  # chars before expansion output is truncated

_EXPAND_RE = re.compile(r'\{\{\s*(.+?)\s*\}\}')


def fetch_messages(pluto_url, since=0):
    """GET /messages?since=<id>. Returns [] on any failure."""
    url = '%s/messages?since=%d' % (pluto_url, since)
    try:
        resp = urlopen(url, timeout=TIMEOUT_HTTP)
        return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return []


def post_message(pluto_url, sender, text):
    """POST /messages {sender, text}. Returns (True, '') or (False, error_str)."""
    url  = '%s/messages' % pluto_url
    body = json.dumps({'sender': sender, 'text': text}).encode('utf-8')
    req  = Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        urlopen(req, timeout=TIMEOUT_HTTP)
        return True, ''
    except Exception as e:
        return False, str(e)


def expand_shell(text, interrupt=None):
    """Replace every {{ command }} in text with the command's stdout.

    interrupt: a threading.Event. When set, the current subprocess is killed
               and the expansion returns '[interrupted]' for that token.
               Subsequent tokens in the same message are also skipped.

    - stdin=DEVNULL so interactive programs fail fast (no hanging prompts).
    - Hard deadline of TIMEOUT_SHELL seconds per token.
    - Output capped at STDOUT_CAP chars.
    """
    def _run(m):
        cmd = m.group(1).strip()

        # If a previous expansion was interrupted, skip remaining tokens.
        if interrupt and interrupt.is_set():
            return '[interrupted]'

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except Exception as e:
            return '[error: %s]' % e

        deadline = time.time() + TIMEOUT_SHELL
        while time.time() < deadline:
            ret = proc.poll()
            if ret is not None:
                out = proc.stdout.read().decode('utf-8', errors='replace').strip()
                if len(out) > STDOUT_CAP:
                    out = out[:STDOUT_CAP] + '[...]'
                return out if out else '[no output]'
            if interrupt and interrupt.is_set():
                proc.kill()
                proc.wait()
                return '[interrupted]'
            time.sleep(0.05)

        proc.kill()
        proc.wait()
        return '[timed out after 5min]'

    return _EXPAND_RE.sub(_run, text)


def has_expansion(text):
    """Return True if text contains at least one {{ }} token."""
    return bool(_EXPAND_RE.search(text))
