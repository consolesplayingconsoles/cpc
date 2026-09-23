#!/usr/bin/env python3
"""
send.py -- copy games from the catalogue onto a node: one contract, a strategy per target.

    plan(root, system, target, sources, files=None, all_missing=False) -> Plan
    STRATEGIES[kind](plan, ctx) -> {"status": "command", "command": str} | {"status": "done", "lines": [...]}

The unit is a COPY of a game: one variant (original, a translation, a mod). A copy is skipped
when the target already holds that game with the same variant label. Otherwise it is taken
from the best other node that holds it (sources = preference order, lab first: it's local),
never from the target itself, and written under its canonical name (names.canonical_name),
never the source file's name.

Strategies, chosen from the target node (strategy_for):
  local    lab            this Mac's library, <ROMS_PATH>/<system>/roms
  batocera batocera       the box's /userdata/roms/<system>, over SSH
  sd       SD_LABEL +     a card in the Pi hub, under SD_ROMS_DIR; ROMs unpacked from .zip
                          (an archive we cannot open, .7z and friends, is skipped, not copied)
           SD_ROMS_DIR
  hdd      PS2_HDD_BYTES  the PS2's APA drive on this Mac: root only, so the answer is the
                          Terminal command (nodes/local/<node>/scripts/ps2hdd.py install)
local, batocera and sd share _files: one file per game, or a disc folder for .gdi/.cue (the
descriptor as <name>.gdi plus the track files it lists, in <name>/), written
beside the target as .part, size-checked, renamed; then the target is rescanned. Arcade systems
keep the source file name (romsets are looked up by it).
  ftp   FTP_PATH        a PS3's webMAN FTP: ISOs into /dev_hdd0/PS3ISO, where webMAN
                          mounts them from (there is no shell on a PS3)
The caller (the API) never branches on the kind: it hands the plan to STRATEGIES.

Pure stdlib, 3.6-safe, ASCII only.
"""
import re

try:
    from . import names, service
except ImportError:
    import names
    import service


class NotAvailable(Exception):
    """This target (or source) can't take part in a send yet: the API's 400 message."""


ARCADE = {"mame", "fbneo", "neogeo", "naomi", "naomi2", "atomiswave", "cps1", "cps2", "cps3", "hikaru", "model2", "model3"}


def strategy_for(cfg, node=None):
    """Which strategy a node declares, or None when it can't take games."""
    if node == "lab":
        return "local" if (cfg.get("ROMS_PATH") or "").strip() else None
    if node == "batocera":
        return "batocera"
    if (cfg.get("PS2_HDD_BYTES") or "").strip():
        return "hdd"
    if (cfg.get("SD_LABEL") or "").strip() and (cfg.get("SD_ROMS_DIR") or "").strip():
        return "sd"
    if (cfg.get("FTP_PATH") or "").strip():
        return "ftp"
    return None


def plan(root, system, target, sources, files=None, all_missing=False):
    """-> {"copies": [{game, name, source: {node, path}}], "skipped": [{game, why}]}.

    files = [{node, path}] picked copies (the drawer), or all_missing = every copy the target
    lacks. sources = node ids allowed as sources, in preference order."""
    view = service.system_view(root, system)
    copies, skipped = [], []
    rank = {n: i for i, n in enumerate(sources)}
    wanted = {(f["node"], f["path"]) for f in files or []}
    for g in view["games"]:
        present = [f for f in g["files"] if f["status"] == "present"]
        on_target = {f["variant"] for f in present if f["node"] == target}
        by_variant = {}
        for f in present:
            if f["node"] == target or f["node"] not in rank:
                continue
            if not all_missing and (f["node"], f["path"]) not in wanted:
                continue
            by_variant.setdefault(f["variant"], []).append(f)
        for variant, candidates in sorted(by_variant.items()):
            if variant in on_target:
                skipped.append({"game": g["title"], "why": "already on %s" % target})
                continue
            best = min(candidates, key=lambda f: (rank[f["node"]], f["path"]))
            copies.append({"game": g["key"], "name": names.canonical_name(g["title"], best),
                           "kind": g.get("kind") or "game",
                           "source": {"node": best["node"], "path": best["path"], "inner": best.get("inner")}})
    return {"copies": copies, "skipped": skipped}


def _hdd(p, ctx):
    """The PS2 drive: one Terminal command. Each copy is `--game NAME SOURCE`; a source is a
    local path, or node:/path for the script to pull over SSH (as the invoking user) first.
    A copy whose source can't be reached from here (an SD card) is skipped, not fatal."""
    args, count = ["install"], 0
    for c in p["copies"]:
        src = ctx["locate"](c["source"])
        if src is None:
            p["skipped"].append({"game": c["name"], "why": "%s's copy can't be read from here yet" % c["source"]["node"]})
            continue
        args += ["--game", c["name"], src]
        count += 1
    if not count:
        return _nothing(ctx)
    return {"status": "command", "command": ctx["command"](args), "count": count}


def _nothing(ctx):
    """Everything is already there: a send is idempotent, so that's a success, not an error."""
    line = "%s already has everything: nothing to copy" % ctx["target"]
    if ctx.get("emit"):
        ctx["emit"](line)
    return {"status": "done", "count": 0, "lines": [line]}


MULTI_FILE = (".cue", ".gdi", ".m3u", ".ccd", ".mds")
# Only .zip can be opened here (stdlib). A card target unpacks the ROM out of the archive, so
# any other archive would be copied in VERBATIM -- and a console that indexes its game folder
# then chokes on a file it cannot read: a .7z dropped in SAROO/ISO stopped the cart booting.
OPAQUE_ARCHIVES = (".7z", ".rar", ".gz", ".xz", ".tar")
DISC_FOLDER = (".gdi", ".cue")      # the multi-file formats a send can carry: descriptor + listed tracks


def disc_tracks(descriptor_text, ext):
    """File names a .gdi / .cue descriptor points at, in order, without duplicates.
    .gdi: first line = track count, then "<n> <lba> <type> <sector> <file> <offset>" where the
    file name may be quoted (spaces). .cue: FILE "<name>" <type> lines."""
    names = []
    if ext.lower() == ".gdi":
        for line in descriptor_text.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            quoted = re.search(r'"([^"]+)"', line)
            parts = line.split()
            name = quoted.group(1) if quoted else (parts[4] if len(parts) >= 5 else None)
            if name and name not in names:
                names.append(name)
    elif ext.lower() == ".cue":
        for m in re.finditer(r'^\s*FILE\s+"?([^"\n]+?)"?\s+\S+\s*$', descriptor_text, re.M | re.I):
            if m.group(1) not in names:
                names.append(m.group(1))
    return names


def _files(p, ctx):
    """File-per-game targets (local, batocera, sd, ftp): copy each source to <dest>/<name><ext>,
    or <dest>/<sub>/<name><ext> when ctx["kind_dirs"] gives the game's kind a folder.
    ctx["card"] does the I/O (mount, exists, put, finish = release + rescan); ctx["unpack"]
    = write the ROM inside a .zip (cards) instead of the archive."""
    card, lines, copied = ctx["card"], [], 0
    kind_dirs = ctx.get("kind_dirs") or {}
    todo = []
    for c in p["copies"]:
        src = ctx["locate"](c["source"])
        ext = ctx["rom_ext"](c["source"]) if ctx.get("unpack") else "." + c["source"]["path"].rsplit(".", 1)[-1]
        if ctx.get("system") in ARCADE:
            c = dict(c, name=c["source"]["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0])
        # a kind with its own folder on the target (a card's Tools/) is written under it
        sub = kind_dirs.get(c.get("kind") or "game")
        if sub:
            c = dict(c, name=sub.rstrip("/") + "/" + c["name"])
        if src is None:
            p["skipped"].append({"game": c["name"], "why": "%s's copy can't be read from here yet" % c["source"]["node"]})
        elif ctx.get("unpack") and ext.lower() in OPAQUE_ARCHIVES:
            p["skipped"].append({"game": c["name"],
                                 "why": "%s can't be unpacked here, and the console can't read an archive" % ext})
        elif ext.lower() in MULTI_FILE and not (ext.lower() in DISC_FOLDER and ctx.get("members")):
            p["skipped"].append({"game": c["name"], "why": "%s disc images can't be sent yet" % ext})
        else:
            todo.append((c, src, ext))
    if not todo:
        return _nothing(ctx)
    card["mount"]()
    try:
        for c, src, ext in todo:
            if ext.lower() in DISC_FOLDER:
                # a disc: its own folder, descriptor renamed to the game, tracks keep their names
                name = c["name"]
                if card["exists"](name):
                    p["skipped"].append({"game": c["name"], "why": "already there as " + name + "/"})
                    continue
                members = ctx["members"](src, ext)
                (ctx.get("emit") or lines.append)("copying %s/ (%d files)" % (name, len(members)))
                for member, filename, is_descriptor in members:
                    card["put"](member, name + "/" + (name + ext if is_descriptor else filename))
                lines.append("copied %s/" % name)
                copied += 1
                continue
            name = c["name"] + ext
            if card["exists"](name):
                p["skipped"].append({"game": c["name"], "why": "already there as " + name})
                continue
            (ctx.get("emit") or lines.append)("copying %s" % name)
            card["put"](src, name)
            lines.append("copied %s" % name)
            copied += 1
    finally:
        for line in card["finish"]():
            (ctx.get("emit") or lines.append)(line)
    (ctx.get("emit") or lines.append)("copied %d game%s" % (copied, "" if copied == 1 else "s"))
    return {"status": "done", "count": copied, "lines": lines}


def _not_built(kind):
    def run(p, ctx):
        raise NotAvailable("sending games to %s (%s) is not built yet" % (ctx["target"], kind))
    return run


# ftp joins _files: the API's card for it speaks the same mount/exists/put/finish words
# over FTP that the others speak over SSH, so the copy loop does not change.
STRATEGIES = {"local": _files, "batocera": _files, "sd": _files, "hdd": _hdd, "ftp": _files}
