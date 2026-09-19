#!/usr/bin/env python3
"""
scan.py -- list one system's ROM dir and read each game's header. READ ONLY.

Runs where the files are. For Batocera that means ON the box: remote_script() packs
headers.py + this file into one `python3 -c` program, so thousands of headers are read
locally over there and only a JSON list comes back over SSH. Locally (tests, ~/cpc)
call scan_dir() directly.

What counts as a game file:
  - everything under the system dir except media/metadata (SKIP_DIRS, SKIP_EXTS) and
    save/state files (`skip`, built from config/consoles.json save/state patterns)
  - .cue / .gdi / .m3u are the game; the track or disc files they name are consumed,
    and the header is read from the first .cue FILE / the .gdi's track 3
  - .zip is opened (stdlib): its main entry's name is recorded as `inner` and the
    header is read from inside it (a zipped .gdi/.cue is followed to its track)
  - .7z/.chd are listed but carry no readable header (name match only)

Output is wrapped in markers so SSH noise (banners, warnings) can't break the JSON.

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
import re
import sys
import zipfile

try:
    from . import headers
except ImportError:
    import headers

SKIP_DIRS = {"images", "videos", "manuals", "media", "downloaded_images", "downloaded_videos",
             "EDMD"}                                   # Mega EverDrive firmware + its saves, not games
# More dirs to walk past, per install rather than per code change: config/consoles.json
# `scanSkipDirs`. A pre-loaded card ships the same games twice -- the Master System
# EverDrive card files all 447 under "ROM A-Z" AND again under "ROM-Europe", "ROM-JAPAN"
# and so on -- and those copies are not extra games, they are the same ones.
SKIP_EXTS = {".xml", ".txt", ".png", ".jpg", ".jpeg", ".mp4", ".pdf", ".cfg", ".srm", ".sav",
             # not games: shortcuts, backups, unfinished downloads, scene/OS leftovers
             ".url", ".lnk", ".old", ".bak", ".tmp", ".part", ".crdownload", ".nfo", ".sfv",
             ".torrent", ".html", ".htm", ".ini", ".db", ".exe",
             ".sub"}                                  # CloneCD subchannel data: part of a disc, not a game
BEGIN, END = "--CPC-SCAN-BEGIN--", "--CPC-SCAN-END--"


def _cue_files(text):
    return re.findall(r'^\s*FILE\s+"?(.+?)"?\s+\w+\s*$', text, re.M | re.I)


def _gdi_tracks(text):
    """-> [(track_no, filename)]; filenames may be quoted and contain spaces."""
    out = []
    for line in text.splitlines()[1:]:
        m = re.match(r'^\s*(\d+)\s+\d+\s+\d+\s+\d+\s+("([^"]+)"|(\S+))\s+\d+\s*$', line)
        if m:
            out.append((int(m.group(1)), m.group(3) or m.group(4)))
    return out


def _read(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except (IOError, OSError):
        return b""


def _skipped(name, skip):
    low = name.lower()
    ext = os.path.splitext(low)[1]
    return (name.startswith(".") or ext in SKIP_EXTS or ext in skip.get("exts", ())
            or low in skip.get("names", ()) or any(c in low for c in skip.get("contains", ())))


def _zip_head(path, skip):
    """-> (inner name, first HEAD_BYTES of the game data) from a zip, or (None, b"")."""
    try:
        zf = zipfile.ZipFile(path)
        entries = [i for i in zf.infolist() if not i.filename.endswith("/")
                   and not i.filename.startswith("__MACOSX") and not _skipped(os.path.basename(i.filename), skip)]
        if not entries:
            return None, b""
        by_name = {i.filename: i for i in entries}
        desc = [i for i in entries if os.path.splitext(i.filename)[1].lower() in (".gdi", ".cue")]
        main = desc[0] if desc else max(entries, key=lambda i: i.file_size)
        target = main
        if desc:
            text = zf.read(main).decode("utf-8", "replace")
            base = os.path.dirname(main.filename)
            if main.filename.lower().endswith(".gdi"):
                named = [fn for no, fn in _gdi_tracks(text) if no == 3]
            else:
                named = _cue_files(text)[:1]
            if named:
                target = by_name.get((base + "/" if base else "") + named[0], main)
        with zf.open(target) as f:
            return os.path.basename(main.filename), f.read(headers.HEAD_BYTES)
    except Exception:
        return None, b""


def scan_dir(sysdir, fmt=None, skip=None):
    """-> [{"path", "size", "header", "inner"}] for every game file under sysdir. fmt =
    the system's header format (consoles.json systems.<x>.header); None = names only. A card
    holding several systems passes {".ext": format, "*": default format} instead.
    skip = {"exts", "names", "contains"} for save/state files (see skip_rules())."""
    skip = skip or {}
    files = []
    for dirpath, dirnames, filenames in os.walk(sysdir):
        skip_dirs = SKIP_DIRS | set(skip.get("dirs") or [])
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs and not d.startswith("."))
        for name in sorted(filenames):
            if _skipped(name, skip):
                continue
            files.append(os.path.relpath(os.path.join(dirpath, name), sysdir))

    consumed, header_file = set(), {}
    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        base = os.path.dirname(rel)
        if ext not in (".cue", ".gdi", ".m3u"):
            continue
        text = _read(os.path.join(sysdir, rel), 65536).decode("utf-8", "replace")
        if ext == ".cue":
            named = _cue_files(text)
            if named:
                header_file[rel] = os.path.join(base, named[0])
        elif ext == ".gdi":
            tracks = _gdi_tracks(text)
            named = [t[1] for t in tracks]
            for no, fn in tracks:
                if no == 3:
                    header_file[rel] = os.path.join(base, fn)
        else:
            named = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
        consumed.update(os.path.normpath(os.path.join(base, n)) for n in named)

    out = []
    for rel in files:
        if os.path.normpath(rel) in consumed:
            continue
        full = os.path.join(sysdir, rel)
        inner = None
        if rel.lower().endswith(".zip"):
            inner, head = _zip_head(full, skip)
        else:
            head = _read(os.path.join(sysdir, header_file.get(rel, rel)), headers.HEAD_BYTES)
        f = (fmt.get(os.path.splitext(inner or rel)[1].lower(), fmt.get("*"))) if isinstance(fmt, dict) else fmt
        out.append({"path": rel, "size": os.path.getsize(full), "inner": inner,
                    "header": headers.read(f, head) if f and head else None})
    return out


def skip_rules(consoles_config):
    """What a scan leaves out, from config/consoles.json: every savePatterns/statePatterns
    entry (an extension or an exact file name), the saveFormats.stateContains substrings
    (batocera's .state1, .state2, ...) and scanSkipDirs (whole directories: a pre-loaded
    card's duplicate region folders)."""
    exts, names_ = set(), set()
    for group in ("savePatterns", "statePatterns"):
        for pats in (consoles_config.get(group) or {}).values():
            for p in pats:
                (exts if p.startswith(".") else names_).add(p.lower())
    contains = [c.lower() for c in ((consoles_config.get("saveFormats") or {}).get("stateContains") or [])]
    return {"exts": sorted(exts), "names": sorted(names_), "contains": contains,
            "dirs": sorted(consoles_config.get("scanSkipDirs") or [])}


def remote_library():
    """headers.py + this module as one self-contained program body, no entry point."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "headers.py")) as f:
        hsrc = f.read()
    with open(os.path.abspath(__file__)) as f:
        ssrc = f.read()
    ssrc = ssrc.replace("try:\n    from . import headers\nexcept ImportError:\n    import headers\n", "")
    return ("import types\nheaders = types.ModuleType('headers')\nexec(%r, headers.__dict__)\n%s\n"
            % (hsrc, ssrc.replace('if __name__ == "__main__":', "if False:")))


def remote_script():
    """`python3 -c <script> <sysdir> [format]` -> one system's scan between markers."""
    return remote_library() + ("print(BEGIN); print(json.dumps(scan_dir(sys.argv[1], "
                               "sys.argv[2] if len(sys.argv) > 2 else None))); print(END)\n")


def parse_output(text):
    """Pull the JSON list out of the remote run's stdout. Raises ValueError if absent,
    so a failed scan never reaches store.merge() (which would mark everything deleted)."""
    a, b = text.find(BEGIN), text.find(END)
    if a < 0 or b < a:
        raise ValueError("scan output missing (remote said: %s)" % text.strip()[-300:])
    return json.loads(text[a + len(BEGIN):b])


if __name__ == "__main__":
    print(json.dumps(scan_dir(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), indent=2))
