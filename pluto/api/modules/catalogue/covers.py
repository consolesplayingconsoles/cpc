#!/usr/bin/env python3
"""
covers.py -- box art for a catalogue game, fetched once and cached on disk.

Source: libretro-thumbnails (github.com/libretro-thumbnails/<repo>/Named_Boxarts), no
account needed. <repo> comes from config/consoles.json `systems.<x>.thumbnails`. Files
there are named by No-Intro/Redump name, which rarely matches a local file exactly
("(USA, Europe)" locally, "(USA, Europe, Brazil) (En)" there). So each system's list of
art names is fetched ONCE (GitHub tree API) and cached; a game matches an art name with
the same names.key(title), preferring the one sharing most of the file's tags. The
exact candidate names are tried first, and are the only route if the list can't load.

Your own art wins over all of it (homebrew, hacks, anything libretro doesn't have):
        catalogue/<system>/art/<game key>.png|jpg|webp   uploaded; never touched by Sync

Cache:  catalogue/<system>/covers/<game key>.png    the art
        catalogue/<system>/covers/<game key>.miss   nothing matched; not asked again
                                                    until clear_misses() (run on Sync)
        catalogue/<system>/covers/_index.json       the repo's art names

Batocera's own scraped images (gamelist.xml <image>/<thumbnail>, from ScreenScraper, which
matches by checksum and so also covers MAME and odd names) are tried before libretro when a
node reader is given: save_cached() stores whatever comes back.

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from . import names
except ImportError:
    import names

TREE = "https://api.github.com/repos/libretro-thumbnails/%s/git/trees/master?recursive=1"
BASE = "https://raw.githubusercontent.com/libretro-thumbnails/%s/master/Named_Boxarts/%s.png"
_UNSAFE = re.compile(r'[&*/:`<>?\\|"]')      # libretro swaps these for "_" in file names


def match_title(game):
    """Title the art is matched on: the label's title when the game has one."""
    if game.get("label"):
        return names.parse(game["label"] + ".png")["title"]    # extension: keep dots in the label
    return game.get("title", "")


def candidates(game):
    """Thumbnail names to try, most specific first (a label, verbatim, before all)."""
    out = [game["label"]] if game.get("label") else []
    # a shelf copy's title is already the full Redump/No-Intro name: the most exact candidate
    for item in game.get("physical") or []:
        if item.get("title") and item["title"] not in out:
            out.append(item["title"])
    files = [f for f in game.get("files", []) if f.get("status") == "present"]
    files.sort(key=lambda f: (bool(f.get("variants")), f["path"]))
    for f in files:
        stem = os.path.splitext(os.path.basename(f["path"]))[0]
        inner = os.path.splitext(f["inner"])[0] if f.get("inner") else None
        p = names.parse(f["path"])
        for n in ([inner] if inner else []) + [stem, ("%s %s" % (p["title"], " ".join("(%s)" % t for t in p["tags"]))).strip()]:
            if n not in out:
                out.append(n)
    if game.get("title") and game["title"] not in out:
        out.append(game["title"])
    return [_UNSAFE.sub("_", n) for n in out]


def _tags(name):
    return {t.strip().lower() for m in re.findall(r"\(([^()]*)\)", name) for t in m.split(",")}


def best_match(game, art_names):
    """Art name with the game's title key, most tags in common with its files; or None."""
    key = names.key(match_title(game))
    # art names carry no extension: add one so parse() doesn't split "L.O.L. - ..." at a dot
    pool = [n for n in art_names if names.key(names.parse(n + ".png")["title"]) == key]
    if not pool:
        return None
    want = _tags(game.get("label") or "")
    for item in game.get("physical") or []:
        want |= _tags(item.get("title") or "")
    for f in game.get("files", []):
        if f.get("status") == "present":
            want |= _tags(os.path.basename(f["path"])) | _tags(f.get("inner") or "")
    return sorted(pool, key=lambda n: (-len(_tags(n) & want), len(n), n))[0]


def _index(root, system, repo, opener, timeout, fallback=False):
    # the system's own repo keeps _index.json; a fallback repo gets its own cache file
    p = os.path.join(_dir(root, system), "_index-%s.json" % repo if fallback else "_index.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    try:
        with opener(Request(TREE % repo, headers={"User-Agent": "cpc-pluto"}), timeout=timeout) as r:
            tree = json.loads(r.read().decode("utf-8"))["tree"]
    except Exception:
        return None                             # not cached: retried on the next ask
    art = sorted(e["path"][len("Named_Boxarts/"):-4] for e in tree
                 if e["path"].startswith("Named_Boxarts/") and e["path"].endswith(".png"))
    with open(p, "w") as f:
        json.dump(art, f)
    return art


def _dir(root, system):
    return os.path.join(root, system, "covers")


ART_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
_MAGIC = [(b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"RIFF", ".webp")]


def custom(root, system, key):
    """Path of an uploaded cover for this game, or None."""
    for ext in ART_TYPES:
        p = os.path.join(root, system, "art", key + ext)
        if os.path.exists(p):
            return p
    return None


def save_custom(root, system, key, data):
    """Store an uploaded cover (type sniffed from its bytes, not trusted from the
    request), replacing any previous one. -> path; raises ValueError if not an image."""
    ext = next((e for magic, e in _MAGIC if data.startswith(magic)), None)
    if ext is None or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise ValueError("not a PNG, JPEG or WebP image")
    d = os.path.join(root, system, "art")
    if not os.path.isdir(d):
        os.makedirs(d)
    for old in ART_TYPES:
        if os.path.exists(os.path.join(d, key + old)):
            os.remove(os.path.join(d, key + old))
    path = os.path.join(d, key + ext)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return path


def linked(root, system, key):
    """True when the catalogue holds an image for this game: an upload or downloaded art."""
    c = cached(root, system, key)
    return bool(custom(root, system, key) or (c and c != "miss"))


def save_cached(root, system, key, data):
    """Cache fetched art (type sniffed: PNG/JPEG/WebP). -> path, or None if not an image."""
    ext = next((e for magic, e in _MAGIC if data.startswith(magic)), None)
    if ext is None or (ext == ".webp" and data[8:12] != b"WEBP"):
        return None
    d = _dir(root, system)
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, key + ext)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    miss = os.path.join(d, key + ".miss")
    if os.path.exists(miss):
        os.remove(miss)
    return path


def forget(root, system, key):
    """Drop the cached art (or miss) for one game so the next view looks it up again."""
    d = _dir(root, system)
    for ext in list(ART_TYPES) + [".miss"]:
        p = os.path.join(d, key + ext)
        if os.path.exists(p):
            os.remove(p)


def cached(root, system, key):
    """Path of the cached art, "miss" when known missing, or None when never tried."""
    d = _dir(root, system)
    for ext in ART_TYPES:
        if os.path.exists(os.path.join(d, key + ext)):
            return os.path.join(d, key + ext)
    if os.path.exists(os.path.join(d, key + ".miss")):
        return "miss"
    return None


def download(url, opener=urlopen, timeout=20, limit=10 * 1024 * 1024):
    """Bytes of an image at a pasted http(s) link, for save_custom(). Raises ValueError on a
    bad link or an oversized body; network errors propagate."""
    if not re.match(r"^https?://", url or "", re.I):
        raise ValueError("link must start with http:// or https://")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Pluto catalogue)", "Accept": "image/*"})
    data = opener(req, timeout=timeout).read(limit + 1)
    if len(data) > limit:
        raise ValueError("image is over 10 MB")
    return data


def fetch(root, system, game, repo, opener=urlopen, timeout=10):
    """Uploaded art, else try each candidate; cache the first hit (or a .miss). -> path or None.
    repo may be a list: the system's own repo, then fallbacks tried in order (Naomi -> Dreamcast)."""
    mine = custom(root, system, game["key"])
    if mine:
        return mine
    got = cached(root, system, game["key"])
    if got:
        return None if got == "miss" else got
    d = _dir(root, system)
    if not os.path.isdir(d):
        os.makedirs(d)
    repos = [r for r in (repo if isinstance(repo, list) else [repo]) if r]
    flaky = False                            # a non-404 failure: don't record a miss we can't be sure of
    all_indexed = True
    for i, repo in enumerate(repos):
        path, repo_flaky, indexed = _fetch_from(root, system, game, repo, d, opener, timeout, fallback=i > 0)
        if path:
            return path
        flaky = flaky or repo_flaky
        all_indexed = all_indexed and indexed
    if repos and not flaky and all_indexed:   # only a clean "not there" everywhere is a miss
        open(os.path.join(d, game["key"] + ".miss"), "w").close()
    return None


def _fetch_from(root, system, game, repo, d, opener, timeout, fallback=False):
    """One thumbnails repo. -> (path or None, transient error seen, index loaded)."""
    tries = candidates(game)
    art = _index(root, system, repo, opener, timeout, fallback)
    if art is not None:
        have = set(art)
        tries = [n for n in tries if n in have]
        best = best_match(game, art)
        if best and best not in tries:
            tries.append(best)
    flaky = False
    for name in tries:
        data, err = _get(opener, BASE % (repo, quote(name)), timeout)
        flaky = flaky or err
        # Duplicate art is a git SYMLINK in those repos: raw serves the link text
        # ("Other Name.png") instead of an image. Follow it once.
        if data and data[:8] != b"\x89PNG\r\n\x1a\n" and len(data) < 512 and data.strip().endswith(b".png"):
            target = data.strip().decode("utf-8", "replace")
            data, err = _get(opener, BASE % (repo, quote(os.path.basename(target)[:-4])), timeout)
            flaky = flaky or err
        if data and data[:8] == b"\x89PNG\r\n\x1a\n":
            path = os.path.join(d, game["key"] + ".png")
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
            return path, flaky, art is not None
    return None, flaky, art is not None


def _get(opener, url, timeout):
    """-> (bytes or None, transient_error). A 404 is a clean "not there"; anything else
    (timeout, rate limit, no network) is transient and must not become a cached miss."""
    try:
        with opener(Request(url, headers={"User-Agent": "cpc-pluto"}), timeout=timeout) as r:
            return r.read(), False
    except Exception as exc:
        return None, getattr(exc, "code", None) != 404


def clear_misses(root, system):
    d = _dir(root, system)
    if os.path.isdir(d):
        for n in os.listdir(d):
            if n.endswith(".miss"):
                os.remove(os.path.join(d, n))
