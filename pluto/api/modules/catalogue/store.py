#!/usr/bin/env python3
"""
store.py -- the per-system catalogue files and the merge that keeps them current.

Layout (catalogue/ is its own private repo, gitignored in cpc):

    catalogue/<system>/digital.json    written by Sync, one entry per file per node
    catalogue/<system>/physical.json   hand-maintained, never written here
    catalogue/<system>/variants.json   hand-maintained credits for mods/translations:
                                       {"<game key>/<name>": {"author": "..."}}
    catalogue/favourites.json          per game: {"games": {"<system>": ["<game key>"]},
                                       "imported": {"<node>/<system>": "<when>"}}

digital.json:

    {"system": "megadrive",
     "games": {"sonic-the-hedgehog": {
         "title": "Sonic the Hedgehog",
         "ids":   ["GM 00001009-00"],
         "files": [{"node": "batocera", "path": "Sonic the Hedgehog (USA, Europe).md",
                    "tags": ["USA, Europe"], "regions": ["USA", "Europe"], "variants": [],
                    "id": "GM 00001009-00", "headerTitle": "SONIC THE HEDGEHOG",
                    "status": "present", "firstSeen": "...", "lastSeen": "..."}]}}}

Regions come from the header only (none when a file has no readable header).
A file is matched to a game by header ID first, then by names.key(title). Variants
(original / translation / mod) come from each file's brackets; a mod or translation
is indexed by names.variant_key() -- game key + name, version stripped.

merge() also returns warnings for cleanup, raised only when a file is first added:
  new-game-variant   a bracketed file matched no game, so it started its own
                     (a mod with its own header/title, or a base game not present yet)
  id-name-mismatch   matched a game by header ID, but its filename title says otherwise
                     (renamed file, or a mod that kept the base header under a new name)
  unbracketed-mod    a file with no brackets joined a game by header ID under a different
                     title (a hack like "Crazy Sonic.zip"): filed as a mod named after its
                     title. Rename it to "<Game> (Region) [Name]" to make that explicit.
  game-rekeyed       a game that only had mods/translations got its first original, so
                     it takes the original's title and key. Callers move favourites and
                     credits with rekey_refs().

Deletes: merge() gets one node's COMPLETE scan. A file that node used to have and no
longer does is marked "deleted" and stays listed (lastSeen = last time it was there);
only a hand edit removes it. If the file comes back it is "present" again.
merge() must never be fed a failed or partial scan -- it would mark everything deleted.

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
import re

try:
    from . import names
except ImportError:     # run as a plain script (test_catalogue.py)
    import names


def empty(system):
    return {"system": system, "games": {}}


def load(root, system):
    p = os.path.join(root, system, "digital.json")
    if not os.path.exists(p):
        return empty(system)
    with open(p) as f:
        return json.load(f)


def save(root, doc):
    d = os.path.join(root, doc["system"])
    if not os.path.isdir(d):
        os.makedirs(d)
    for g in doc["games"].values():
        g["files"].sort(key=lambda f: (f["node"], f["path"]))
    tmp = os.path.join(d, "digital.json.tmp")
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(d, "digital.json"))


def find_game(doc, title, game_id=None, header_title=None):
    """Key of the game this title/ID belongs to, or None. ID first, then name.

    Some publishers reused a product ID across different games (Saturn GS-9079 is both
    Virtua Fighter 2 and "VF. KIDS"): an ID match only counts when the internal header
    titles agree too, whenever both sides have one."""
    if game_id:
        for k, g in doc["games"].items():
            if game_id not in g["ids"]:
                continue
            theirs = [f.get("headerTitle") for f in g["files"] if f.get("id") == game_id and f.get("headerTitle")]
            if not header_title or not theirs or any(names.same_title(header_title, t) for t in theirs):
                return k
    k = names.key(title)
    return k if k in doc["games"] else None


def load_credits(root, system):
    p = os.path.join(root, system, "variants.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def _stripped(path, strip):
    """The path a title is read from, with every match of `strip` (a regex) cut out.

    It runs against the WHOLE path, so a rule can name the folder it applies to:
    "(?<=ROM A-Z/)[0-9]{3}\\s" numbers only the Master System card's own folder and leaves
    "007 James Bond" in the SG-1000 folder alone.
    """
    return re.sub(strip, "", path) if strip else path


def _drop_shared_ids(scan, strip=None):
    """Forget a header ID that this scan hands to more than one game.

    A cartridge header is only worth trusting when it identifies ONE game. Pre-loaded packs
    are full of placeholder codes -- on the Master System EverDrive card 00000 is shared by
    16 games and 166665 by 9 -- and grouping on those files Altered Beast under Bomber Raid.

    Only region-named dumps ("Altered Beast (USA, Europe)") count towards a clash. Two of
    those under one ID means the ID is junk. A hack carries its base game's ID under its own
    bare name ("Crazy Sonic.zip") ON PURPOSE -- that is how it finds its base -- so bare
    names never make an ID untrustworthy.
    """
    titles = {}
    for item in scan:
        gid = (item.get("header") or {}).get("id")
        if not gid:
            continue
        p = names.parse(_stripped(item["path"], strip))
        if p["variants"] or not names.has_region_tag(p["tags"]):
            continue                              # a hack shares its base game's ID on purpose
        titles.setdefault(gid, set()).add(names.key(p["title"]))
    shared = {gid for gid, ts in titles.items() if len(ts) > 1}
    if not shared:
        return scan
    out = []
    for item in scan:
        h = item.get("header") or {}
        out.append(dict(item, header=dict(h, id=None)) if h.get("id") in shared else item)
    return out


def merge(doc, node, scan, now, scope=None, strip=None):
    """Fold one node's complete scan into doc (in place). -> (counts, warnings, renames).

    renames: {old game key: new game key} -- pass to rekey_refs().
    scope: a path prefix ("SAROO2/") when the scan covers only PART of a node, e.g. one of
    several SD cards: only that node's files under the prefix can be marked deleted, so
    scanning one card never deletes the other card's games.
    strip: a regex cut off the FILE NAME before it is read as a title, for a card that
    numbers its games ("034 Assault City (Europe).sms"). The stored path is untouched --
    it is where the file really is -- only the name the title comes from.

    A scan item may also carry "name": the name to read the title from when the path does
    not hold one. A PS3 install is a folder called BLES00107 and its real title lives in
    PARAM.SFO, so the scanner passes "SEGA Rally (Europe).ps3" while the path stays the
    folder it can actually be read from.

    scan: [{"path": "...", "header": {"id", "title"} or None}, ...]
    """
    scan = _drop_shared_ids(scan, strip)
    counts = {"added": 0, "present": 0, "deleted": 0, "restored": 0}
    warnings, renames = [], {}
    have = {}
    for gk, g in doc["games"].items():
        for f in g["files"]:
            if f["node"] == node and (not scope or f["path"].startswith(scope)):
                have[f["path"]] = f

    # Originals first, so a base game names its own entry before a mod that shares its
    # header can create one under the mod's filename title. Among originals, No-Intro style
    # names (with a "(Region)" tag) go before bare names: a bare "Crazy Sonic.zip" hack must
    # not name the retail Sonic it shares a header with.
    def parse(path):
        return names.parse(_stripped(path, strip))

    def parse_item(i):
        return names.parse(i["name"]) if i.get("name") else parse(i["path"])

    def order(i):
        p = parse_item(i)
        return (bool(p["variants"]), not names.has_region_tag(p["tags"]), i["path"])
    seen = set()
    for item in sorted(scan, key=order):
        path, header = item["path"], item.get("header")
        seen.add(path)
        f = have.get(path)
        if f is not None:
            if f["status"] == "deleted":
                f["status"] = "present"
                counts["restored"] += 1
            else:
                counts["present"] += 1
            f["lastSeen"] = now
            if item.get("inner"):
                f["inner"] = item["inner"]
            continue

        p = parse_item(item)
        gid = header["id"] if header else None
        gk = find_game(doc, p["title"], gid, header["title"] if header else None)
        existing = gk is not None
        if gk is None:
            gk = names.key(p["title"]) or path
            doc["games"][gk] = {"title": p["title"], "ids": [], "files": []}
            if p["variants"]:
                warnings.append({"code": "new-game-variant", "node": node, "path": path, "game": gk})
        game = doc["games"][gk]
        # A region-named original ("Soukyuu Gurentai (Japan)") joining a game that was named
        # after a BARE file ("SOUKYU_GURENTAI.cue", maybe from another node's earlier scan):
        # the region-named dump names the game; bare originals under another title become mods.
        if existing and gid and not p["variants"] and names.has_region_tag(p["tags"]) and names.key(p["title"]) != gk \
                and not any(not f["variants"] and names.has_region_tag(f["tags"]) for f in game["files"]):
            new_key = names.key(p["title"])
            if new_key and new_key not in doc["games"]:
                for f in game["files"]:
                    t = names.parse(f["path"])["title"]
                    if not f["variants"] and not names.same_title(t, p["title"]):
                        f["variants"] = [{"kind": "mod", "name": t, "version": f.get("version")}]
                game["title"] = p["title"]
                doc["games"][new_key] = doc["games"].pop(gk)
                for old, new in list(renames.items()):
                    if new == gk:
                        renames[old] = new_key
                renames.setdefault(gk, new_key)
                warnings.append({"code": "game-rekeyed", "node": node, "path": path, "game": new_key, "from": gk})
                gk = new_key
                existing = False
        # A bracket-less file that joined by header ID under a DIFFERENT title is a hack of
        # that game, not another dump: file it as a mod named after its own title. Regions
        # and re-spelled dumps keep the same title key, so they stay originals.
        if existing and gid and not p["variants"] and not names.same_title(p["title"], game["title"]) \
                and any(not f["variants"] for f in game["files"]):
            p["variants"] = [{"kind": "mod", "name": p["title"], "version": p["version"]}]
            warnings.append({"code": "unbracketed-mod", "node": node, "path": path, "game": gk})
            existing = False                     # already reported: no id-name-mismatch too
        if not p["variants"] and game["files"] and all(f["variants"] for f in game["files"]):
            new_key = names.key(p["title"]) or gk
            game["title"] = p["title"]
            if new_key != gk and new_key not in doc["games"]:
                doc["games"][new_key] = doc["games"].pop(gk)
                for old, new in list(renames.items()):
                    if new == gk:
                        renames[old] = new_key
                renames.setdefault(gk, new_key)
                warnings.append({"code": "game-rekeyed", "node": node, "path": path, "game": new_key, "from": gk})
                gk = new_key
        if existing and gid and names.key(p["title"]) != gk:
            warnings.append({"code": "id-name-mismatch", "node": node, "path": path, "game": gk, "id": gid})
        if gid and gid not in game["ids"]:
            game["ids"].append(gid)
        game["files"].append({
            "node": node, "path": path, "tags": p["tags"], "version": p["version"],
            "regions": header["regions"] if header else [], "variants": p["variants"],
            "id": gid, "headerTitle": header["title"] if header else None, "inner": item.get("inner"),
            "card": item.get("card"),              # SD card label, for games on a console's cards
            # What the thing IS, when its platform says so (a PS3's PARAM.SFO CATEGORY):
            # HG boots on its own, GD is the install half of a disc game and cannot.
            "category": item.get("category") or None,
            "status": "present", "firstSeen": now, "lastSeen": now,
        })
        counts["added"] += 1

    for path, f in have.items():
        if path not in seen and f["status"] == "present":
            f["status"] = "deleted"
            counts["deleted"] += 1
    return counts, warnings, renames


def variants(game):
    """{"original": [files], "T-Cat": [files], ...} for the detail view."""
    out = {}
    for f in game["files"]:
        out.setdefault(names.variant_label(f["variants"]), []).append(f)
    return out


def apply_scraped(doc, node, scraped):
    """Attach a node's scraper data ({rel path: {"name", "image", "thumbnail", ...}}) to
    that node's files, for covers. Files the scraper doesn't know keep what they had."""
    for g in doc["games"].values():
        for f in g["files"]:
            s = scraped.get(os.path.normpath(f["path"])) if f["node"] == node else None
            if s:
                f["scraped"] = {"name": s["name"], "image": s["image"], "thumbnail": s["thumbnail"]}


def load_labels(root):
    """Pluto's own display names, {system: {game key: label}} (labels.json). A label names a
    game whose files can't carry a good name (SAROO's kof95.bin) and drives its art lookup."""
    p = os.path.join(root, "labels.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def save_labels(root, labels):
    tmp = os.path.join(root, "labels.json.tmp")
    with open(tmp, "w") as f:
        json.dump({s: v for s, v in labels.items() if v}, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, os.path.join(root, "labels.json"))


def rekey_labels(labels, system, renames):
    """Move a system's labels to the games' new keys after merge() renamed them (in place)."""
    mine = labels.get(system) or {}
    for old, new in renames.items():
        if old in mine and new not in mine:
            mine[new] = mine.pop(old)


def load_kinds(root):
    """What each non-game entry is, {system: {game key: kind}} (kinds.json). Only "tool" for
    now: boot discs, browsers, loaders (Dreamkey, DreamShell). Unlisted = a game. Keyed by
    game, so a physical tool and its digital copy are one entry."""
    p = os.path.join(root, "kinds.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def save_kinds(root, kinds):
    """Write kinds.json back (see load_kinds), dropping systems left with nothing."""
    p = os.path.join(root, "kinds.json")
    body = {s: v for s, v in sorted(kinds.items()) if v}
    with open(p + ".tmp", "w") as f:
        json.dump(body, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(p + ".tmp", p)


def load_hardware(root):
    """Hardware you physically own (hardware.json):
    {"consoles": {system: {"model", "region", "status", "notes"}},
     "peripherals": [{"name", "model", "systems": [system...], "count", "storage", "status", "notes"}]}
    Peripherals = flashcarts/ODEs, memory cards, controllers and other input (systems empty =
    general purpose). status/notes are free text and only record what's missing or wrong."""
    p = os.path.join(root, "hardware.json")
    if not os.path.exists(p):
        return {"consoles": {}}
    with open(p) as f:
        return json.load(f)


def load_favourites(root):
    p = os.path.join(root, "favourites.json")
    if not os.path.exists(p):
        return {"games": {}, "imported": {}}
    with open(p) as f:
        return json.load(f)


def save_favourites(root, favs):
    for keys in favs["games"].values():
        keys.sort()
    if "systems" in favs:
        favs["systems"] = sorted(set(favs["systems"]))
    tmp = os.path.join(root, "favourites.json.tmp")
    with open(tmp, "w") as f:
        json.dump(favs, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(root, "favourites.json"))


def import_favourites(favs, doc, node, scraped, now):
    """ONE-TIME: copy a node's favourite flags into favs as game keys. Once imported for
    this node+system it is never read again -- ours is the single source of truth, so a
    later un-star here isn't undone by the node. -> number of games added, or None if
    this node+system was already imported."""
    mark = "%s/%s" % (node, doc["system"])
    if mark in favs["imported"]:
        return None
    by_path = {}
    for gk, g in doc["games"].items():
        for f in g["files"]:
            if f["node"] == node:
                by_path[os.path.normpath(f["path"])] = gk
    keys = favs["games"].setdefault(doc["system"], [])
    added = 0
    for path, s in scraped.items():
        gk = by_path.get(path)
        if s.get("favorite") and gk and gk not in keys:
            keys.append(gk)
            added += 1
    favs["imported"][mark] = now
    return added


def rekey_refs(favs, credits, system, renames):
    """Move favourites (favs["games"][system]) and credit keys ("<game key>/<name>") to a
    game's new key after merge() renamed it. Both dicts are changed in place."""
    keys = favs["games"].get(system, [])
    for i, k in enumerate(keys):
        keys[i] = renames.get(k, k)
    favs["games"][system] = sorted(set(keys))
    for ck in list(credits):
        game, _, name = ck.partition("/")
        if game in renames:
            credits["%s/%s" % (renames[game], name)] = credits.pop(ck)
