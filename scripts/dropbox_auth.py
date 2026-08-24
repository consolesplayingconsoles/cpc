#!/usr/bin/env python3
"""
dropbox_auth.py -- get a Dropbox REFRESH token, once, so Pluto stops expiring.

Why this exists: Dropbox has no durable API key. The App Console's "Generate" button
issues a SHORT-LIVED access token (the 'sl.' prefix, ~4 hours), and long-lived tokens
were withdrawn in 2021 -- so a pasted token takes every cloud feature down with it a
few hours later. The fix is to authorise ONCE with token_access_type=offline and keep
the refresh token, which does not expire; the API mints access tokens from it as needed.

You have to approve in a browser, so this cannot be fully automated. It takes a minute.

    python3 scripts/dropbox_auth.py

Reads DROPBOX_APP_KEY / DROPBOX_APP_SECRET from nodes/cloud/dropbox/.env when they are
already there, otherwise asks. Both are on your app's page at
https://www.dropbox.com/developers/apps (Settings -> App key / App secret).

Prints the lines to paste into nodes/cloud/dropbox/.env. It deliberately does NOT write
that file: it holds your live credentials and is not in git.

Pure stdlib, ASCII output only.
"""
import json
import os
import sys
import urllib.parse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "nodes", "cloud", "dropbox", ".env")

AUTHORIZE = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropbox.com/oauth2/token"


def read_env(path):
    cfg = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


def ask(prompt, current=""):
    if current:
        return current
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\naborted.")
        sys.exit(1)


def main():
    cfg = read_env(ENV_PATH)
    print("CPC -- Dropbox one-time authorisation")
    print("-" * 60)

    key = ask("App key:    ", cfg.get("DROPBOX_APP_KEY", ""))
    if not key:
        print("\n  ERROR: an app key is required.\n")
        return 2
    secret = ask("App secret: ", cfg.get("DROPBOX_APP_SECRET", ""))
    if not secret:
        print("\n  ERROR: an app secret is required.\n")
        return 2
    if cfg.get("DROPBOX_APP_KEY"):
        print("  (using the app key/secret already in %s)" % ENV_PATH)

    # No redirect_uri -> Dropbox shows the code on screen for you to paste back.
    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "client_id":         key,
        "response_type":     "code",
        "token_access_type": "offline",     # <- this is what yields a refresh token
    })
    print("\n1. Open this in a browser and approve the app:\n")
    print("   " + url)
    print("\n2. Dropbox will show you an authorisation code. Paste it here.\n")
    code = ask("Code: ")
    if not code:
        print("\n  ERROR: no code given.\n")
        return 2

    data = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "code":          code,
        "client_id":     key,
        "client_secret": secret,
    }).encode()
    req = Request(TOKEN_URL, data=data,
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        rep = json.loads(urlopen(req, timeout=30).read().decode())
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace").strip()[:300]
        except Exception:
            pass
        print("\n  ERROR: exchange failed (HTTP %d). %s" % (exc.code, body))
        print("  Codes are single-use and expire fast -- re-run and use a fresh one.\n")
        return 1
    except Exception as exc:
        print("\n  ERROR: couldn't reach Dropbox: %s\n" % exc)
        return 1

    refresh = rep.get("refresh_token", "")
    if not refresh:
        print("\n  ERROR: no refresh_token came back. The authorise URL must carry")
        print("  token_access_type=offline -- re-run this script rather than reusing")
        print("  an older URL.\n")
        return 1

    print("\n" + "-" * 60)
    print("Done. Put these in %s" % ENV_PATH)
    print("-" * 60 + "\n")
    print("DROPBOX_APP_KEY=%s"       % key)
    print("DROPBOX_APP_SECRET=%s"    % secret)
    print("DROPBOX_REFRESH_TOKEN=%s" % refresh)
    print("\nThen drop the old DROPBOX_TOKEN line (it is ignored once the three")
    print("above are set) and restart the API. It should not need doing again.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
