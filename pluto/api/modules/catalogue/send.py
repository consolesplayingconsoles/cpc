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
  gdemu SD_LAYOUT=gdemu a GDEMU card: a game per numbered slot after openMenu's 01, and
                          openMenu's game list (OPENMENU.INI in 01's image) rewritten in place
The caller (the API) never branches on the kind: it hands the plan to STRATEGIES.

Pure stdlib, 3.6-safe, ASCII only.
"""
import re
import threading

try:
    from . import names, service
except ImportError:
    import names
    import service


class NotAvailable(Exception):
    """This target (or source) can't take part in a send yet: the API's 400 message."""


class SourceUnavailable(NotAvailable):
    """One copy could not be read from its source node (the node is off, the file is gone).
    Non-blocking: _files skips that game with this reason and carries on with the rest."""


# A source read failing like this means the whole node is off, not just that one file:
# the rest of its copies are skipped at once instead of each waiting out the SSH timeout.
UNREACHABLE = ("ssh: connect to host", "Could not resolve hostname", "Connection refused",
               "Connection timed out", "Operation timed out", "No route to host")


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
        # a GDEMU card is numbered slots (01 = the menu), not a folder of games
        return "gdemu" if (cfg.get("SD_LAYOUT") or "").strip().lower() == "gdemu" else "sd"
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

    A disc is a folder of tracks, so when no OTHER copy on the same card lives in the disc's
    own folder, that folder is the target: deleting only the .cue would leave the bins. Only
    a disc descriptor takes its folder, and only its OWN folder (the one it sits in): a ROM in
    a kind folder (Tools/, Mods/) is just the file -- taking the top folder deleted every
    other tool with it.

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
    if "/" not in path or not path.lower().endswith(MULTI_FILE):
        return path
    folder = path.rsplit("/", 1)[0]
    others = [f for f in peers if f["path"] != path and f["path"].startswith(folder + "/")]
    return path if others else folder


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
    down = {}                                   # source node -> why it can't be reached
    try:
        for c, src, ext in todo:
            node = c["source"]["node"]
            if node in down:
                p["skipped"].append({"game": c["name"], "why": down[node]})
                continue
            try:
                copied += _copy_one(c, src, ext, card, ctx, p, lines)
            except SourceUnavailable as e:
                p["skipped"].append({"game": c["name"], "why": str(e)})
                if any(u in str(e) for u in UNREACHABLE):
                    down[node] = "%s is off or unreachable" % node
                    (ctx.get("emit") or lines.append)("%s is unreachable: skipping its games" % node)
    finally:
        for line in card["finish"]():
            (ctx.get("emit") or lines.append)(line)
    (ctx.get("emit") or lines.append)("copied %d game%s" % (copied, "" if copied == 1 else "s"))
    return {"status": "done", "count": copied, "lines": lines}


def _copy_one(c, src, ext, card, ctx, p, lines):
    """Write one planned copy to the target -> 1 if written, 0 if it was already there."""
    verb = "replacing" if c.get("replace") else "copying"
    done = "replaced" if c.get("replace") else "copied"
    if ext.lower() in DISC_FOLDER:
        # a disc: its own folder, descriptor renamed to the game, tracks keep their names
        name = c["name"]
        if card["exists"](name) and not c.get("replace"):
            p["skipped"].append({"game": c["name"], "why": "already there as " + name + "/"})
            return 0
        members = ctx["members"](src, ext)
        (ctx.get("emit") or lines.append)("%s %s/ (%d files)" % (verb, name, len(members)))
        for member, filename, is_descriptor in members:
            card["put"](member, name + "/" + (name + ext if is_descriptor else filename))
        lines.append("%s %s/" % (done, name))
        return 1
    name = c["name"] + ext
    if card["exists"](name) and not c.get("replace"):
        p["skipped"].append({"game": c["name"], "why": "already there as " + name})
        return 0
    (ctx.get("emit") or lines.append)("%s %s" % (verb, name))
    card["put"](src, name)
    lines.append("%s %s" % (done, name))
    return 1


# ---------------------------------------------------------------------------------------------
# GDEMU: a card of numbered slots. 01 is openMenu (its own disc image); a game is one slot,
# NN/disc.gdi + trackNN.<ext> (or NN/disc.cdi) + name.txt + serial.txt. openMenu only lists what
# OPENMENU.INI inside 01's image says, so a send also rewrites that list -- the same entries
# GDMENUCardManager writes (FillListText), in place in the space the file already has.
# ---------------------------------------------------------------------------------------------
GDEMU_MENU = "01"
GDEMU_MAX_SLOT = 99
# One GDEMU send at a time: each rewrites openMenu's whole list, so two at once (a send per game)
# each wrote the list as THEY saw the card and the last to finish dropped the other's game.
_GDEMU_LOCK = threading.Lock()


def ipbin_fields(ip):
    """openMenu's per-game fields from a Dreamcast IP.BIN (the 0x100-byte meta block), read the
    way GDMENUCardManager reads them: disc "1/1" unless the header numbers it, vga = the 6th
    peripherals character is '1', product = the serial without dashes, up to its first space."""
    if ip[:16] != b"SEGA SEGAKATANA ":
        raise ValueError("not a Dreamcast IP.BIN")
    txt = lambda a, n: ip[a:a + n].decode("ascii", "replace").strip()
    no, total = ip[0x2B:0x2C], ip[0x2D:0x2E]
    disc = "1/1" if b" " in (no, total) else "%s/%s" % (no.decode("ascii", "replace"), total.decode("ascii", "replace"))
    serial = txt(0x40, 10)
    return {"name": txt(0x80, 128), "disc": disc, "vga": "1" if ip[0x38 + 5:0x38 + 6] == b"1" else "0",
            "region": txt(0x30, 8), "version": txt(0x4A, 6), "date": txt(0x50, 8),
            "serial": serial, "product": serial.replace("-", "").split(" ")[0]}


INI_KEYS = ("name", "disc", "vga", "region", "version", "date", "product")


def parse_openmenu_ini(text):
    """OPENMENU.INI -> {slot number: {field: value}}."""
    items = {}
    for line in text.splitlines():
        m = re.match(r"^(\d+)\.(\w+)=(.*)$", line.strip())
        if m:
            items.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3)
    return items


def openmenu_ini(items):
    """{slot: fields} -> OPENMENU.INI text, Card Manager's layout (LF, a blank line per item)."""
    out = ["[OPENMENU]", "num_items=%d" % len(items), "", "[ITEMS]"]
    for n in sorted(items):
        for k in INI_KEYS:
            out.append("%02d.%s=%s" % (n, k, items[n].get(k, "")))
        out.append("")
    return "\n".join(out) + "\n"


def gdemu_gdi(text, tracks):
    """Rewrite a .gdi for a GDEMU slot: its track files renamed trackNN.<ext> (no quotes, no
    spaces, which GDEMU's parser does not take). tracks = disc_tracks(text) order ->
    (new descriptor text, {old name: new name})."""
    rename = {t: "track%02d%s" % (i + 1, ("." + t.rsplit(".", 1)[-1].lower()) if "." in t else "")
              for i, t in enumerate(tracks)}
    lines = text.splitlines()
    out = [lines[0].strip()]
    for line in lines[1:]:
        if not line.strip():
            continue
        quoted = re.search(r'"([^"]+)"', line)
        parts = line.split()
        name = quoted.group(1) if quoted else parts[4]
        head = line[:quoted.start()].split() if quoted else parts[:4]
        tail = line[quoted.end():].split() if quoted else parts[5:]
        out.append(" ".join(head + [rename[name]] + tail))
    return "\r\n".join(out) + "\r\n", rename


def gdi_ipbin_track(text):
    """(track file, sector size) holding a GDI's IP.BIN: the first data track (type 4) of the
    high-density area (LBA >= 45000)."""
    for line in text.splitlines()[1:]:
        quoted = re.search(r'"([^"]+)"', line)
        parts = line.split()
        if len(parts) >= 5 and parts[2] == "4" and int(parts[1]) >= 45000:
            return (quoted.group(1) if quoted else parts[4]), int(parts[3])
    raise ValueError("no high-density data track in the .gdi")


def _iso_dir(read_lba, lba, length):
    """ISO9660 directory records: [(name, lba, length, is_dir, dir lba, offset in that dir)]."""
    out, data = [], b"".join(read_lba(lba + i) for i in range((length + 2047) // 2048))
    p = 0
    while p < len(data):
        n = data[p]
        if n == 0:
            p = (p // 2048 + 1) * 2048
            continue
        rec = data[p:p + n]
        name = rec[33:33 + rec[32]]
        if name not in (b"\0", b"\1"):
            out.append((name.decode("ascii", "replace").split(";")[0], int.from_bytes(rec[2:6], "little"),
                        int.from_bytes(rec[10:14], "little"), bool(rec[25] & 2), lba + p // 2048, p % 2048))
        p += n
    return out


def menu_ini_location(gdi_text, read_track):
    """Where OPENMENU.INI sits in a GDEMU menu image.

    gdi_text = 01's disc.gdi; read_track(file, offset, length) -> bytes from that track file.
    -> {file, offset, length, room, record: (file, offset)} -- the INI's bytes, how many it may
    grow to without touching the next file on the disc, and its directory record."""
    tracks = []
    for line in gdi_text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 5 and parts[2] == "4":
            tracks.append((int(parts[1]), parts[4]))
    tracks.sort()

    def where(lba):
        start, f = max(t for t in tracks if t[0] <= lba)
        return f, (lba - start) * 2048

    def read_lba(lba):
        f, off = where(lba)
        return read_track(f, off, 2048)
    hd = min(t[0] for t in tracks if t[0] >= 45000)
    pvd = read_lba(hd + 16)
    if pvd[1:6] != b"CD001":
        raise ValueError("01 is not an ISO9660 menu disc")
    root = pvd[156:190]
    entries, todo = [], [(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"))]
    while todo:
        for e in _iso_dir(read_lba, *todo.pop()):
            entries.append(e)
            if e[3]:
                todo.append((e[1], e[2]))
    ini = [e for e in entries if e[0].upper() == "OPENMENU.INI"]
    if not ini:
        raise ValueError("01 has no OPENMENU.INI: is it openMenu?")
    _, lba, length, _, dlba, doff = ini[0]
    after = [e[1] for e in entries if e[1] > lba] + [lba + (length + 2047) // 2048]
    f, off = where(lba)
    rf, roff = where(dlba)
    return {"file": f, "offset": off, "length": length, "room": (min(after) - lba) * 2048,
            "record": (rf, roff + doff)}


def card_slot_fields(read, exists, slot):
    """openMenu fields for a slot already on the card, from its own disc header: disc.gdi's
    high-density data track, or the IP.BIN signature inside disc.cdi. read(name, offset, length),
    exists(name) -- reading a file that is not on the card is an error, not an empty answer."""
    d = "%02d/" % slot
    name = read(d + "name.txt", 0, 512).decode("utf-8", "replace").strip() if exists(d + "name.txt") else ""
    if exists(d + "disc.gdi"):
        gdi = read(d + "disc.gdi", 0, 64 * 1024)
        track, sector = gdi_ipbin_track(gdi.decode("ascii", "replace"))
        ip = read(d + track, 16 if sector == 2352 else 0, 0x100)
    else:
        ip, off, sig = b"", 0, b"SEGA SEGAKATANA "
        while not ip:
            chunk = read(d + "disc.cdi", off, 4 << 20)
            if not chunk:
                raise NotAvailable("slot %02d has no disc.gdi and no Dreamcast header in disc.cdi" % slot)
            i = chunk.find(sig)
            ip = read(d + "disc.cdi", off + i, 0x100) if i >= 0 else b""
            off += len(chunk) - len(sig)
    return dict(ipbin_fields(ip), name=name or ipbin_fields(ip)["name"])


def _gdemu(p, ctx):
    """GDEMU card: each copy into the next slot after the highest, then openMenu's list rebuilt
    from the slots on the card. ctx["card"] adds read / patch / put_bytes to the usual words;
    ctx["read_src"](src, offset, length) reads a source file (its IP.BIN)."""
    card, lines, copied = ctx["card"], [], 0
    emit = ctx.get("emit") or lines.append
    if not p["copies"]:
        return _nothing(ctx)
    if not _GDEMU_LOCK.acquire(blocking=False):
        emit("another send to the GDEMU card is running: waiting for it to finish")
        _GDEMU_LOCK.acquire()
    try:
        return _gdemu_locked(p, ctx, card, lines, emit)
    finally:
        _GDEMU_LOCK.release()


def _gdemu_locked(p, ctx, card, lines, emit):
    copied = 0
    card["mount"]()
    try:
        slots = sorted({int(f.split("/")[0]) for f in card["files"]() if re.match(r"^\d\d/", f)})
        if GDEMU_MENU not in ["%02d" % s for s in slots]:
            raise NotAvailable("the card has no slot 01 (openMenu): set it up with GDMENUCardManager first")
        gaps = [n for n in range(1, max(slots) + 1) if n not in slots]
        if gaps:
            raise NotAvailable("slot %02d is missing, and GDEMU needs them in a row: renumber the card "
                               "with GDMENUCardManager first" % gaps[0])
        gdi01 = card["read"](GDEMU_MENU + "/disc.gdi", 0, 64 * 1024).decode("ascii", "replace")
        loc = menu_ini_location(gdi01, lambda f, o, n: card["read"](GDEMU_MENU + "/" + f, o, n))
        items = parse_openmenu_ini(card["read"](GDEMU_MENU + "/" + loc["file"], loc["offset"], loc["length"])
                                   .decode("latin-1"))
        new = {}
        for c in p["copies"]:
            src = ctx["locate"](c["source"])
            if src is None:
                p["skipped"].append({"game": c["name"], "why": "%s's copy can't be read from here yet" % c["source"]["node"]})
                continue
            ext = "." + c["source"]["path"].rsplit(".", 1)[-1].lower()
            if ext not in (".gdi", ".cdi"):
                p["skipped"].append({"game": c["name"], "why": "GDEMU takes .gdi and .cdi, not %s" % ext})
                continue
            slot = max(slots) + 1
            if slot > GDEMU_MAX_SLOT:
                raise NotAvailable("the card is full (%d slots)" % GDEMU_MAX_SLOT)
            d = "%02d/" % slot
            emit("copying %s into slot %02d" % (c["name"], slot))
            if ext == ".gdi":
                members = ctx["members"](src, ext)
                text = ctx["read_src"](members[0][0], 0, 64 * 1024).decode("ascii", "replace")
                gdi, rename = gdemu_gdi(text, [m[1] for m in members[1:]])
                ip_file, sector = gdi_ipbin_track(text)
                ip_src = next(m[0] for m in members[1:] if m[1] == ip_file)
                ip = ctx["read_src"](ip_src, 16 if sector == 2352 else 0, 0x100)
                for member, filename, _ in members[1:]:
                    card["put"](member, d + rename[filename])
                card["put_bytes"](gdi.encode("ascii"), d + "disc.gdi")
            else:
                ip = ctx["find_ipbin"](src)
                card["put"](src, d + "disc.cdi")
            fields = ipbin_fields(ip)
            card["put_bytes"](c["name"].encode("utf-8"), d + "name.txt")
            card["put_bytes"](fields["serial"].encode("ascii"), d + "serial.txt")
            new[slot] = dict(fields, name=c["name"])
            slots.append(slot)
            copied += 1
            lines.append("copied %s into slot %02d" % (c["name"], slot))
        if new:
            # the list as the card is NOW: re-read it right before writing, keep entries for slots
            # that still exist, add the new ones, and read the header of any slot on the card the
            # list is missing (one written by another tool, or lost to an older send)
            items = parse_openmenu_ini(card["read"](GDEMU_MENU + "/" + loc["file"], loc["offset"], loc["length"])
                                       .decode("latin-1"))
            for s in slots:
                if s not in items and s not in new:
                    new[s] = card_slot_fields(card["read"], card["exists"], s)
                    emit("slot %02d was missing from openMenu's list: added from its disc header" % s)
            ini = openmenu_ini({s: new.get(s) or items[s] for s in slots}).encode("latin-1", "replace")
            if len(ini) > loc["room"]:
                raise NotAvailable("openMenu's list needs %d bytes but the menu disc has room for %d: "
                                   "rebuild the menu with GDMENUCardManager" % (len(ini), loc["room"]))
            # the INI's bytes (zero-filled to the old length), then its directory record's size
            card["patch"](GDEMU_MENU + "/" + loc["file"], loc["offset"], ini + bytes(max(0, loc["length"] - len(ini))))
            rf, roff = loc["record"]
            card["patch"](GDEMU_MENU + "/" + rf, roff + 10, len(ini).to_bytes(4, "little") + len(ini).to_bytes(4, "big"))
            back = card["read"](GDEMU_MENU + "/" + loc["file"], loc["offset"], len(ini))
            if back != ini:
                raise NotAvailable("openMenu's list did not read back as written: the card may be failing")
            emit("openMenu list rebuilt: %d items" % len(slots))
    finally:
        for line in card["finish"]():
            emit(line)
    emit("copied %d game%s" % (copied, "" if copied == 1 else "s"))
    return {"status": "done", "count": copied, "lines": lines}


def _not_built(kind):
    def run(p, ctx):
        raise NotAvailable("sending games to %s (%s) is not built yet" % (ctx["target"], kind))
    return run


# ftp joins _files: the API's card for it speaks the same mount/exists/put/finish words
# over FTP that the others speak over SSH, so the copy loop does not change.
STRATEGIES = {"local": _files, "batocera": _files, "sd": _files, "hdd": _hdd, "ftp": _files,
              "gdemu": _gdemu}
