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


def _ours(f):
    """A copy WE made (a cpc translation or mod), as opposed to someone else's release.

    It matters for sending: a third-party ROM is immutable, so a target that has it needs
    nothing. Ours carries the same catalogue name from one build to the next while its BYTES
    change every time -- so "the target already has it" is never a reason to skip it."""
    return any((v.get("author") or "").strip().lower() == "cpc" for v in (f.get("variants") or []))


GAME_TOKEN = "<game>"        # in SD_SEND_DIRS: one folder per base game, e.g. Mods/<game>
_UNSAFE_NAME = re.compile(r'[/\\:*?"<>|]')


def _safe_name(text):
    """A title as a folder name a cart's file browser can hold (no path characters)."""
    return _UNSAFE_NAME.sub("-", text).strip().rstrip(".") or "Unnamed"


RANGE_TOKEN = "<range>"      # in SD_SEND_DIRS: split games into A-C / D-F ... folders


def pick_range(name, ranges):
    """Which of a card's letter-range folders a name belongs in ("Sonic..." -> "R-S").

    ranges are the folder names themselves, in order, each "<first>-<last>" or a single
    letter; "0-9-D" means digits through D. The last range takes anything after it, the
    first takes anything before, so a name can never fall outside the card's layout.
    """
    if not ranges:
        return ""
    ch = (name or "").strip()[:1].upper()
    ch = ch if ch.isalpha() else "0"
    for r in ranges:
        parts = r.split("-")
        lo, hi = parts[0][:1].upper(), parts[-1][:1].upper()
        lo = lo if lo.isalpha() else "0"
        hi = hi if hi.isalpha() else "0"
        if lo <= ch <= hi:
            return r
    return ranges[-1] if ch > "A" else ranges[0]


def kind_sub(sub, copy, ranges=None):
    """A kind's sub-folder for one copy, tokens filled in: "Mods/Sonic The Hedgehog", "R-S".

    A cart menu indexes one directory at a time -- the EverDrive-MD OS tops out near 200
    files, and past that the browser garbles and sorts at random -- so games split into
    letter-range folders and mods go in a folder per base game instead of all beside the
    games they patch.
    """
    if GAME_TOKEN in sub:
        sub = sub.replace(GAME_TOKEN, _safe_name(copy.get("title") or copy.get("game") or ""))
    if RANGE_TOKEN in sub:
        sub = sub.replace(RANGE_TOKEN, pick_range(copy.get("name") or copy.get("title") or "", ranges or []))
    return sub.strip("/")


def variant_file_name(copy, per_game_folder=False):
    """What a mod is CALLED on a card: "<game> [<mod> by <author> v<version>]".

    The only thing dropped is the REGION, which is what split a game's mods apart on the
    card -- one hack of Sonic 1 was filed "(USA, Europe)" while the rest said "(Japan, USA,
    Europe)", so they sorted nowhere near each other. Nothing else is touched: the mod's
    name is whatever the file says, word for word, capitals and all. It is not ours to
    rewrite, so "Michael-Jackson-Moonwalker-Thriller-Hack" stays exactly that.

    "by <author>" travels with it, because that is what tells a later send this copy is ours
    and a rebuild REPLACES it (_ours) -- and it is how homebrew names its builds, so the Lab
    file and the card copy read as the same thing.
    -> None when the copy is not a mod at all.
    """
    v = copy.get("variant") or {}
    name = (v.get("name") or "").strip()
    if not name:
        return None
    author = (v.get("author") or "").strip()
    if author and ("by " + author).lower() not in name.lower():
        name += " by " + author
    version = (v.get("version") or "").strip()
    if version and not name.lower().endswith(version.lower()):
        name += " v" + version.lstrip("vV")
    name = _safe_name(name)
    title = (copy.get("title") or "").strip()
    # A hack distributed under a bare file name carries the game in that name ("Streets of
    # Rage 2 - Looney Tunes Edition"), so "<game> [<mod>]" would say the game twice. Only a
    # DASHED whole-title prefix comes off, which is the file-name idiom: a pun keeps its
    # words ("Sonic & Knuckles + Sonic 3", "Super Mario 46", "Tokyo BS Guide").
    if title and name.lower().startswith(title.lower() + " - "):
        rest = name[len(title) + 3:].strip()
        if rest and rest[0].isalnum():
            name = rest
    if per_game_folder or not title:
        return "[%s]" % name if per_game_folder else name
    return "%s [%s]" % (_safe_name(title), name)


def kind_sub(sub, copy, ranges=None):
    """A kind's sub-folder for one copy, tokens filled in: "Mods/Sonic The Hedgehog", "R-S".

    A cart menu indexes one directory at a time -- the EverDrive-MD OS tops out near 200
    files, and past that the browser garbles and sorts at random -- so games split into
    letter-range folders and mods go in a folder per base game instead of all beside the
    games they patch.
    """
    if GAME_TOKEN in sub:
        sub = sub.replace(GAME_TOKEN, _safe_name(copy.get("title") or copy.get("game") or ""))
    if RANGE_TOKEN in sub:
        sub = sub.replace(RANGE_TOKEN, pick_range(copy.get("name") or copy.get("title") or "", ranges or []))
    return sub.strip("/")


def card_target(path, card, peers):
    """What a delete must actually remove on a node, given a catalogue copy's stored path.

    A copy on a card is stored with the CARD LABEL in front ("SAROO/<game>/<game>.cue"),
    because one node can own several cards. That label is not a folder on the card -- the
    node's write base already points inside it -- so it comes off first. With it in the
    path the target did not exist, and `rm -rf` on a missing path exits 0: the delete
    looked like it worked while the file stayed put and the next scan brought it back.

    A disc is a folder of tracks, so when no OTHER copy on the same card lives under that
    folder, the folder itself is the target: deleting only the .cue would leave the bins.

    path/card come from the copy; peers are the node's other copies (each {path, card}).
    -> the path to remove, relative to the node's ROM base.
    """
    card = (card or "").strip()
    if card and path.split("/")[0] == card:
        path = path[len(card) + 1:]
        peers = [dict(f, path=f["path"][len(card) + 1:]) for f in peers
                 if (f.get("card") or "").strip() == card and f["path"].startswith(card + "/")]
    else:
        peers = [f for f in peers if (f.get("card") or "").strip() == card]
    if "/" not in path:
        return path
    top = path.split("/")[0]
    others = [f for f in peers if f["path"] != path and f["path"].split("/")[0] == top]
    return path if others else top


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
            best = min(candidates, key=lambda f: (rank[f["node"]], f["path"]))
            replace = variant in on_target
            if replace and not _ours(best):
                skipped.append({"game": g["title"], "why": "already on %s" % target})
                continue
            # Mod-ness belongs to the file (its [bracket] variant), while a kind like "tool"
            # belongs to the game. A copy with a variant is a mod copy, so it is filed with
            # the mods even though its game is the plain retail game.
            # ("game" is what the view calls a game with no kind of its own, so it is not a
            # kind to route by -- reading it as one filed every mod among the games.)
            own_kind = g.get("kind") if g.get("kind") not in (None, "", "game") else None
            kind = own_kind or ("mod" if best.get("variants") else "game")
            copies.append({"game": g["key"], "name": names.canonical_name(g["title"], best),
                           "kind": kind, "replace": replace,
                           # a card's layout needs the base game and the mod this copy is
                           "title": g["title"], "variant": (best.get("variants") or [{}])[0],
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
        # a kind with its own folder on the target (a card's Tools/, Mods/<game>/, A-C/)
        sub = kind_dirs.get(c.get("kind") or "game")
        if sub:
            sub = kind_sub(sub, c, ctx.get("ranges"))
            raw = kind_dirs.get(c.get("kind") or "game") or ""
            own = None if raw == RANGE_TOKEN else variant_file_name(c, GAME_TOKEN in raw)
            c = dict(c, name=sub + "/" + (own or c["name"]))
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
                if card["exists"](name) and not c.get("replace"):
                    p["skipped"].append({"game": c["name"], "why": "already there as " + name + "/"})
                    continue
                members = ctx["members"](src, ext)
                verb = "replacing" if c.get("replace") else "copying"
                (ctx.get("emit") or lines.append)("%s %s/ (%d files)" % (verb, name, len(members)))
                for member, filename, is_descriptor in members:
                    card["put"](member, name + "/" + (name + ext if is_descriptor else filename))
                lines.append("%s %s/" % ("replaced" if c.get("replace") else "copied", name))
                copied += 1
                continue
            name = c["name"] + ext
            if card["exists"](name) and not c.get("replace"):
                p["skipped"].append({"game": c["name"], "why": "already there as " + name})
                continue
            verb = "replacing" if c.get("replace") else "copying"
            (ctx.get("emit") or lines.append)("%s %s" % (verb, name))
            card["put"](src, name)
            lines.append("%s %s" % ("replaced" if c.get("replace") else "copied", name))
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
