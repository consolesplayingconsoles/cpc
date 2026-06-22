"""Substack sender — turn an `@substack post` chat message into a DRAFT.

Substack has no public API; the endpoints below are reverse-engineered community
knowledge, re-expressed here in pure stdlib (urllib + http.cookiejar) so Pluto stays
dependency-free. The 3rd-party `python-substack` was reference only — no code copied.

SAFETY: this only ever creates a DRAFT (private to the author's account) and replies
with the editor URL. Publishing stays a human action in Substack — Pluto never makes
anything public. Password-login accounts only.

UNVERIFIED: like the dreamehome password grant, this path is built but not self-tested
(no creds on hand, and we don't hit a real account from here). Confirm it on the first
real login; the failure messages below name what to check if an endpoint drifted.
"""
import json
import urllib.request
import urllib.error
import http.cookiejar

_SUBSTACK = "https://substack.com"
_UA = "Mozilla/5.0 (CPC Pluto)"
_TIMEOUT = 30


def _opener():
    """An opener that carries cookies across requests (the session lives in the jar)."""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _post(opener, url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "User-Agent":   _UA,
    })
    with opener.open(req, timeout=_TIMEOUT) as r:
        body = r.read().decode("utf-8") or "{}"
    return json.loads(body)


def _http_error_detail(e):
    """Read the response body from an HTTPError for diagnosis."""
    try:
        detail = e.read().decode("utf-8", errors="replace")
        if detail:
            return detail[:300]
    except Exception:
        pass
    return ""



def _login(opener, email, password):
    """POST the login form; the session cookie lands in the opener's jar. Returns the
    response body (which may carry the user object)."""
    return _post(opener, _SUBSTACK + "/api/v1/login", {
        "email": email, "password": password,
        "captcha_response": "", "for_pub": "", "redirect": "/",
    })



def _doc(body_text):
    """A minimal Substack/ProseMirror document: one paragraph per non-empty line."""
    paras = [{"type": "paragraph", "content": [{"type": "text", "text": line}]}
             for line in body_text.split("\n") if line.strip()]
    return {"type": "doc", "content": paras or [{"type": "paragraph"}]}


def _split_title_body(content):
    """Convention: first line is the title, the rest is the body."""
    lines = content.strip().split("\n")
    title = lines[0].strip() if lines else ""
    body  = "\n".join(lines[1:]).strip()
    return title, body


def post(creds, content):
    """Create a Substack DRAFT from `content` (first line = title, rest = body).

    `creds` is the substack node's env dict. Returns (ok, message) — the message is
    posted back into the chat as the @substack reply (the draft URL, or why it failed).
    """
    email = (creds.get("SUBSTACK_EMAIL") or "").strip()
    password = (creds.get("SUBSTACK_PASSWORD") or "").strip()
    pub = (creds.get("SUBSTACK_PUBLICATION_URL") or "").strip().rstrip("/")
    if not (email and password and pub):
        return False, ("not configured -- add SUBSTACK_EMAIL, SUBSTACK_PASSWORD and "
                       "SUBSTACK_PUBLICATION_URL to nodes/cloud/substack/.env, then restart.")

    title, body = _split_title_body(content)
    if not title:
        return False, "give me something to draft: '@substack post <title>' (then optional body lines)."

    opener = _opener()
    try:
        login_body = _login(opener, email, password)
    except urllib.error.HTTPError as e:
        detail = _http_error_detail(e)
        if e.code in (401, 403):
            return False, ("login rejected (HTTP %d). Password accounts only -- "
                           "check creds or set a password in Substack Settings. %s" % (e.code, detail)).strip()
        return False, ("login failed: HTTP %d. %s" % (e.code, detail)).strip()
    except Exception as e:
        return False, "login error: %s" % e

    draft = {
        "draft_title":    title,
        "draft_subtitle": "",
        "draft_body":     json.dumps(_doc(body)),
        "draft_bylines":  [],
        "audience":       "everyone",
        "type":           "newsletter",
    }

    resp = None
    try:
        resp = _post(opener, pub + "/api/v1/drafts", draft)
    except urllib.error.HTTPError as e:
        # Substack returns 400 on bylines validation but still writes the draft.
        # Parse the response body for the id before giving up.
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
            resp = json.loads(raw) if raw else {}
        except Exception:
            resp = {}
        if not (resp or {}).get("id"):
            return False, ("draft creation failed: HTTP %d. %s" % (e.code, raw[:300])).strip()
    except Exception as e:
        return False, "draft error: %s" % e

    draft_id = (resp or {}).get("id")
    if not draft_id:
        return False, ("login worked but the draft came back without an id -- check "
                       "SUBSTACK_PUBLICATION_URL (should be https://<you>.substack.com).")
    return True, "drafted \"%s\" -> %s/publish/post/%s (review & publish from Substack)." % (
        title, pub, draft_id)
