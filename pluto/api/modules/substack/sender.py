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


def _get(opener, url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": _UA})
    with opener.open(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _login(opener, email, password):
    """POST the login form; the session cookie lands in the opener's jar. Returns the
    response body (which may carry the user object)."""
    return _post(opener, _SUBSTACK + "/api/v1/login", {
        "email": email, "password": password,
        "captcha_response": None, "for_pub": "", "redirect": "/",
    })


def _user_id(opener, login_body):
    """Best-effort author id for the draft byline. Try the login body, then the
    subscription endpoint; return None to fall back to no explicit byline."""
    for key in ("user", "user_data"):
        u = login_body.get(key)
        if isinstance(u, dict) and u.get("id"):
            return u["id"]
    if login_body.get("user_id"):
        return login_body["user_id"]
    try:
        sub = _get(opener, _SUBSTACK + "/api/v1/subscription")
        return sub.get("user_id") or (sub.get("user") or {}).get("id")
    except Exception:
        return None


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

    try:
        opener = _opener()
        login_body = _login(opener, email, password)
        uid = _user_id(opener, login_body)

        draft = {
            "draft_title":    title,
            "draft_subtitle": "",
            "draft_body":     json.dumps(_doc(body)),
            "audience":       "everyone",
            "type":           "newsletter",
        }
        if uid is not None:
            draft["draft_bylines"] = [{"id": uid, "is_guest": False}]

        resp = _post(opener, pub + "/api/v1/drafts", draft)
        draft_id = resp.get("id")
        if not draft_id:
            return False, ("login worked but the draft came back without an id -- check "
                           "SUBSTACK_PUBLICATION_URL (should be https://<you>.substack.com).")
        return True, "drafted \"%s\" -> %s/publish/post/%s (review & publish from Substack)." % (
            title, pub, draft_id)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, ("login rejected (HTTP %d). This path supports PASSWORD accounts only "
                           "-- check the creds, or that the account isn't magic-link-only." % e.code)
        return False, "substack request failed: HTTP %d. (endpoints are RE'd -- may need a refresh.)" % e.code
    except Exception as e:
        return False, "substack draft failed: %s" % e
