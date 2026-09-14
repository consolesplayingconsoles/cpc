#!/usr/bin/env python3
"""
service.py -- what the /catalogue routes do, kept out of api.py.

Sync (read-only against every node):
  batocera   ONE ssh run of scan.remote_script() over /userdata/roms (all systems, or one),
             plus each system's gamelist.xml. Nothing on the box is written.
  lab        this machine's ROM library, pluto/.env ROMS_PATH, laid out as
             <ROMS_PATH>/<system>/roms/ (only the roms/ dir is read). Skipped when unset.
  other      nodes that host the system (config/consoles.json nodeConsoles) are reported
             as not built yet -- SD cards come next.
  saves      the Dropbox /saves/<system> ledger, when a lookup is given: which nodes hold
             a save for which ROM stem.

View (what the Media tab reads): digital files and physical.json items merged into ONE
entry per game. Physical items match like files do -- header ID, then name -- so an
original GD-ROM on the shelf and a modded ROM of it are the same row.

physical.json (hand-maintained):
    {"items": [{"title": "Shenmue", "id": "HDR-0073", "format": "GD-ROM", "notes": ""}]}

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

try:
    from . import covers, gamelist, metadata, names, scan, store
except ImportError:
    import covers, gamelist, metadata, names, scan, store

BATOCERA_ROMS = "/userdata/roms"
_LIST_MARK = "--CPC-GAMELIST--"


def load_physical(root, system):
    p = os.path.join(root, system, "physical.json")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return json.load(f).get("items", [])


def systems(root):
    """Systems that hold at least one digital file or physical item."""
    out = []
    if not os.path.isdir(root):
        return out
    for system in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, system)) or system.startswith("."):
            continue
        view = system_view(root, system)
        if view["games"]:
            out.append({"system": system, "games": len(view["games"]),
                        "nodes": sorted({n for g in view["games"] for n in g["nodes"]}),
                        "physical": sum(1 for g in view["games"] if g["physical"])})
    return out


def system_view(root, system):
    """-> {"system", "games": [...sorted by title], "warnings": []} for the tab."""
    doc = store.load(root, system)
    favs = set(store.load_favourites(root)["games"].get(system, []))
    labels = store.load_labels(root).get(system) or {}
    credits = store.load_credits(root, system)
    saves = doc.get("saves", {})

    games = {}
    for gk, g in doc["games"].items():
        files = []
        for f in g["files"]:
            stem = os.path.splitext(os.path.basename(f["path"]))[0].lower()
            f = dict(f, save=saves.get(stem, []), variant=names.variant_label(f["variants"]))
            for v in f["variants"]:
                # Hand-kept credits (variants.json) win over an author read from the filename.
                v["author"] = (credits.get(names.variant_key(gk, v)) or {}).get("author") or v.get("author")
            files.append(f)
        games[gk] = {"key": gk, "title": g["title"], "ids": g["ids"], "files": files, "physical": [],
                     "meta": g.get("meta") or {}}

    for item in load_physical(root, system):
        gk = store.find_game(doc, item.get("title", ""), item.get("id")) or names.key(item.get("title", ""))
        if gk not in games:
            games[gk] = {"key": gk, "title": item.get("title", gk), "ids": [], "files": [], "physical": [], "meta": {}}
        games[gk]["physical"].append(item)

    out = []
    for g in games.values():
        present = [f for f in g["files"] if f["status"] == "present"]
        g["nodes"] = sorted({f["node"] for f in present})
        g["regions"] = sorted({r for f in present for r in f["regions"]})
        g["saves"] = sorted({n for f in g["files"] for n in f["save"]})
        g["favourite"] = g["key"] in favs
        g["label"] = labels.get(g["key"])
        if g["label"]:
            g["fileTitle"], g["title"] = g["title"], g["label"]
        c = covers.custom(root, system, g["key"]) and "custom" or covers.cached(root, system, g["key"])
        g["cover"] = c if c in ("custom", "miss") else ("cached" if c else None)
        out.append(g)
    out.sort(key=lambda g: names.key(g["title"]))
    return {"system": system, "games": out, "syncedAt": doc.get("syncedAt")}


def cover(root, system, game_key, consoles_config, read_node_file=None):
    """Cover path for one game, or None. Order: upload, cache, the node's own scraped image
    (read_node_file(node, path) -> bytes, e.g. Batocera over SSH), then libretro."""
    game = next((g for g in system_view(root, system)["games"] if g["key"] == game_key), None)
    if game is None:
        return None
    if covers.custom(root, system, game_key):
        return covers.custom(root, system, game_key)
    c = covers.cached(root, system, game_key)
    if c and c != "miss":
        return c
    if read_node_file:
        for f in game["files"]:
            s = f.get("scraped") or {}
            # Batocera's <thumbnail> is the BOX art; <image> is a screenshot. Covers only.
            for rel in (s.get("thumbnail"),):
                if f["status"] != "present" or not rel or f["node"] != "batocera":
                    continue
                full = rel if rel.startswith("/") else "/userdata/roms/%s/%s" % (system, rel)
                try:
                    data = read_node_file("batocera", full)
                except Exception:
                    data = None
                path = covers.save_cached(root, system, game_key, data) if data else None
                if path:
                    return path
    repo = ((consoles_config.get("systems") or {}).get(system) or {}).get("thumbnails")
    return covers.fetch(root, system, game, repo)


def missing_covers(root):
    """Present games with no image linked in the catalogue (no upload, no downloaded art),
    across all systems. Local only: a game whose art was never fetched counts as missing."""
    out = []
    for s in systems(root):
        system = s["system"]
        for g in system_view(root, system)["games"]:
            if (g["nodes"] or g["physical"]) and not covers.linked(root, system, g["key"]):
                out.append({"system": system, "key": g["key"], "title": g["title"]})
    return {"games": out}


def set_label(root, system, game_key, label):
    """Set (or clear, label empty) a game's label. Its art is looked up again on next view:
    the cached match (or miss) is dropped, uploads stay."""
    label = (label or "").strip()
    labels = store.load_labels(root)
    mine = labels.setdefault(system, {})
    if label:
        mine[game_key] = label
    else:
        mine.pop(game_key, None)
    store.save_labels(root, labels)
    covers.forget(root, system, game_key)


def set_favourite(root, system, game_key, on):
    favs = store.load_favourites(root)
    keys = favs["games"].setdefault(system, [])
    if on and game_key not in keys:
        keys.append(game_key)
    if not on and game_key in keys:
        keys.remove(game_key)
    store.save_favourites(root, favs)


def _batocera_script():
    """scan + gamelist for one system or '*' (every non-empty roms dir), one program.
    Run as `python3 - <system|*> <roms root> <json formats> <json skip>` with this on stdin."""
    return scan.remote_library() + '''
import os as _os
_root, _want, _formats, _skip = sys.argv[2], sys.argv[1], json.loads(sys.argv[3]), json.loads(sys.argv[4])
_out = {}
for _s in sorted(_os.listdir(_root)):
    _d = _os.path.join(_root, _s)
    if (_want != "*" and _s != _want) or not _os.path.isdir(_d):
        continue
    _files = scan_dir(_d, _formats.get(_s), _skip)
    if not _files:
        continue
    _gl = ""
    if _os.path.exists(_os.path.join(_d, "gamelist.xml")):
        with open(_os.path.join(_d, "gamelist.xml"), "rb") as _f:
            _gl = _f.read().decode("utf-8", "replace")
    _out[_s] = {"files": _files, "gamelist": _gl}
print("%s"); print(json.dumps(_out)); print("%s")
''' % (_LIST_MARK, _LIST_MARK)


def parse_batocera(text):
    """Raises ValueError when the run didn't complete, so nothing gets merged."""
    a = text.find(_LIST_MARK)
    b = text.find(_LIST_MARK, a + 1)
    if a < 0 or b < 0:
        raise ValueError("batocera scan did not complete: %s" % text.strip()[-300:])
    return json.loads(text[a + len(_LIST_MARK):b])


def header_formats(consoles_config):
    """{system: header format} from config/consoles.json `systems`."""
    return {s: c["header"] for s, c in (consoles_config.get("systems") or {}).items() if c.get("header")}


def sd_script():
    """Scanner for a card in the Pi hub: mounts it read-only by label at the hub's own
    mountpoint (only if not mounted), scans <mount>/<roms_dir>, unmounts only if it mounted.
    Run as `python3 - <label> <roms_dir> <json header format(s) or ''> <json skip>` with this on stdin."""
    return scan.remote_library() + '''
import os as _o, subprocess as _sp
_label, _dir, _fmt, _skip = sys.argv[1], sys.argv[2], json.loads(sys.argv[3] or "null"), json.loads(sys.argv[4])
_dev = "/dev/disk/by-label/" + _label
_mnt = "/mnt/cpc-sd/" + "".join(c for c in _label if c.isalnum() or c in "-_")
if not _o.path.exists(_dev):
    print("no card labelled %s in the hub" % _label); sys.exit(2)
_ours = not _o.path.ismount(_mnt)
if _ours:
    _sp.run(["sudo", "mkdir", "-p", _mnt], check=True)
    _sp.run(["sudo", "mount", "-o", "ro", _dev, _mnt], check=True)
try:
    _root = _o.path.join(_mnt, _dir)
    print(BEGIN); print(json.dumps(scan_dir(_root, _fmt, _skip) if _o.path.isdir(_root) else [])); print(END)
finally:
    if _ours:
        _sp.run(["sudo", "umount", _mnt])
'''


def sd_routes(consoles_config, systems_of):
    """{".ext": system, "*": default} for a card that holds several systems: a file goes to
    the node system whose consoles.json `extensions` list its extension, else to the node's
    first system (a Mega EverDrive card: .sms -> mastersystem, everything else megadrive)."""
    cfg = consoles_config.get("systems") or {}
    route = {"*": systems_of[0]}
    for s in systems_of:
        for ext in (cfg.get(s) or {}).get("extensions") or []:
            route[ext.lower()] = s
    return route


def _scan_sd(run_ssh, hub_node, labels, roms_dir, fmt, skip):
    """One node's SD cards via the Pi hub -> {label: [files]}; a card that isn't in the
    hub is simply absent (its games stay as they were)."""
    out = {}
    for label in labels:
        rc, text = run_ssh(hub_node, ["python3", "-", label, roms_dir, json.dumps(fmt) if fmt else "", json.dumps(skip)], stdin=sd_script())
        try:
            out[label] = scan.parse_output(text)
        except ValueError:
            out.setdefault("_skipped", []).append("%s (%s)" % (label, text.strip()[-120:]))
    return out


def sync(root, system, consoles_config, run_ssh, saves_lookup, emit, now, roms=BATOCERA_ROMS, lab_roms=None, sd_nodes=None):
    """Sync one system ('*' = everything). emit(line) streams progress.
    consoles_config = config/consoles.json (nodeConsoles for hosts, systems for headers).

    run_ssh(node, argv, stdin=None) -> (rc, output); saves_lookup(system) -> {stem: [nodes]} or None.
    lab_roms = this machine's ROMS_PATH (None = no lab source).
    sd_nodes = {node: {"labels": [...], "roms_dir": "SAROO/ISO", "hub": "pi"}} for consoles
    whose games live on SD cards read through the Pi hub (node .env SD_LABEL / SD_ROMS_DIR).

    Two phases. SCANS run in parallel, one thread per node: they only read. MERGES then
    run one at a time on this thread, because two nodes can write the same system's
    digital.json. Nothing blocks: a node or system that fails is WARNed and skipped
    (its entries untouched) and the rest carry on. emit is only called from this thread.
    Returns {"merged": n, "skipped": n}.
    """
    skip = scan.skip_rules(consoles_config)
    formats = header_formats(consoles_config)
    ignored = set(consoles_config.get("ignoreSystems") or [])   # ports Batocera restores on boot
    node_consoles = consoles_config.get("nodeConsoles") or {}
    hosts = [n for n, cs in sorted(node_consoles.items()) if system == "*" or "*" in cs or system in cs]
    label = "all systems" if system == "*" else system

    jobs = {}
    if "batocera" in hosts:
        jobs["batocera"] = lambda: _scan_batocera(run_ssh, system, roms, formats, skip)
    if "lab" in hosts and lab_roms:
        jobs["lab"] = lambda: _scan_local(system, lab_roms, formats, skip)
    sd_nodes = sd_nodes or {}
    for node in hosts:
        sd = sd_nodes.get(node)
        if sd and sd.get("labels") and sd.get("roms_dir"):
            systems_of = [c for c in (node_consoles.get(node) or []) if c != "*"]
            if systems_of and (system == "*" or system in systems_of):
                route = sd_routes(consoles_config, systems_of)
                fmt = {ext: formats.get(s) for ext, s in route.items()} if len(systems_of) > 1 else formats.get(systems_of[0])
                jobs[node] = (lambda sd=sd, route=route, fmt=fmt:
                              {"__sd__": route, "cards": _scan_sd(run_ssh, sd.get("hub", "pi"), sd["labels"], sd["roms_dir"], fmt, skip)})
    for node in hosts:
        if node not in jobs and (system != "*" or "*" in node_consoles[node]):
            emit("%s: %s, skipped" % (node, "no ROMS_PATH set" if node == "lab" else "not built yet"))
    for node in sorted(jobs):
        emit("%s: scanning %s" % (node, label))

    results = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {node: pool.submit(fn) for node, fn in jobs.items()}
            for node, fut in sorted(futures.items()):
                try:
                    results[node] = fut.result()
                except Exception as exc:
                    emit("WARN %s: scan failed, skipped, nothing changed (%s)" % (node, exc))

    # One Dropbox ledger read per system per run, however many nodes merge into it.
    saves_cache = {}
    def saves_once(s):
        if s not in saves_cache:
            try:
                saves_cache[s] = saves_lookup(s) if saves_lookup else None
            except Exception as exc:
                emit("WARN saves/%s: ledger unreadable, save badges unchanged (%s)" % (s, exc))
                saves_cache[s] = None
        return saves_cache[s]

    merged = skipped = 0
    favs = store.load_favourites(root)
    for node, found in sorted(results.items()):
        if "__sd__" in found:
            route = found["__sd__"]
            for missing_card in found["cards"].pop("_skipped", []):
                emit("WARN %s: card %s skipped, nothing changed" % (node, missing_card))
            for label, files in sorted(found["cards"].items()):
                by_system = {s: [] for s in sorted(set(route.values())) if system in ("*", s)}
                for f in files:
                    s = route.get(os.path.splitext(f.get("inner") or f["path"])[1].lower(), route["*"])
                    if s in by_system:
                        by_system[s].append(dict(f, path="%s/%s" % (label, f["path"]), card=label))
                for s, prefixed in by_system.items():
                    try:
                        _merge_system(root, s, node, {"files": prefixed, "gamelist": ""}, favs, saves_once, emit, now,
                                      ((consoles_config.get("systems") or {}).get(s) or {}).get("thumbnails"), scope=label + "/")
                        merged += 1
                    except Exception as exc:
                        emit("WARN %s/%s[%s]: merge failed, skipped (%s)" % (node, s, label, exc)); skipped += 1
            continue
        # "*" also revisits systems this node USED to have, so an emptied dir is marked
        # deleted instead of silently keeping its old list.
        targets = [system] if system != "*" else sorted(set(found) | _systems_with_node(root, node))
        for s in targets:
            if s in ignored:
                continue
            data = found.get(s, {"files": [], "gamelist": ""})
            if not data["files"] and not os.path.exists(os.path.join(root, s, "digital.json")):
                continue
            try:
                _merge_system(root, s, node, data, favs, saves_once, emit, now,
                              ((consoles_config.get("systems") or {}).get(s) or {}).get("thumbnails"))
                merged += 1
            except Exception as exc:
                emit("WARN %s/%s: merge failed, skipped, nothing changed (%s)" % (node, s, exc))
                skipped += 1
    if results and os.path.isdir(root):
        store.save_favourites(root, favs)
    skipped += len(jobs) - len(results)
    emit("done: %d merged, %d skipped" % (merged, skipped))
    return {"merged": merged, "skipped": skipped}


def _scan_batocera(run_ssh, system, roms, formats, skip):
    """-> {system: {"files", "gamelist"}}; raises when the run didn't complete."""
    # The program goes over STDIN, not `python3 -c`: Batocera's dropbear resets any command
    # line over ~9000 chars, and the scanner (headers + zip + skip rules) is past that.
    rc, out = run_ssh("batocera", ["python3", "-", system, roms, json.dumps(formats), json.dumps(skip)],
                      stdin=_batocera_script())
    return parse_batocera(out)


def _scan_local(system, roms_root, formats, skip):
    """A local library: <roms_root>/<system>/roms/. Only dirs holding a roms/ dir count,
    so bios/, backups and card copies next to it are ignored. -> {system: {...}}"""
    roms_root = os.path.expanduser(roms_root)
    if not os.path.isdir(roms_root):
        raise IOError("ROMS_PATH %s not found" % roms_root)
    present = sorted(s for s in os.listdir(roms_root) if os.path.isdir(os.path.join(roms_root, s, "roms")))
    out = {}
    for s in ([system] if system != "*" else present):
        d = os.path.join(roms_root, s, "roms")
        if os.path.isdir(d):
            out[s] = {"files": scan.scan_dir(d, formats.get(s), skip), "gamelist": ""}
    return out


def _systems_with_node(root, node):
    out = set()
    if os.path.isdir(root):
        for s in os.listdir(root):
            if os.path.exists(os.path.join(root, s, "digital.json")):
                doc = store.load(root, s)
                if any(f["node"] == node for g in doc["games"].values() for f in g["files"]):
                    out.add(s)
    return out


def _merge_system(root, system, node, found, favs, saves_lookup, emit, now, thumbnails=None, scope=None):
    doc = store.load(root, system)
    counts, warnings, renames = store.merge(doc, node, found["files"], now, scope)
    scraped = gamelist.parse(found["gamelist"]) if found["gamelist"] else {}
    store.apply_scraped(doc, node, scraped)
    imported = store.import_favourites(favs, doc, node, scraped, now)
    if renames:
        labels = store.load_labels(root)
        if labels.get(system):
            store.rekey_labels(labels, system, renames)
            store.save_labels(root, labels)
        credits = store.load_credits(root, system)
        store.rekey_refs(favs, credits, system, renames)
        if credits:
            _save_json(os.path.join(root, system, "variants.json"), credits)
    saves = saves_lookup(system) if saves_lookup else None
    if saves is not None:
        doc["saves"] = saves
    doc["syncedAt"] = now
    if thumbnails:
        try:
            metadata.annotate(root, system, doc, thumbnails)
        except Exception as exc:
            emit("WARN meta/%s: metadata unavailable, kept what was there (%s)" % (system, exc))
    store.save(root, doc)
    covers.clear_misses(root, system)       # new files may match art that didn't before

    emit("%s/%s: %d added, %d present, %d deleted, %d restored%s" % (
        node + ("[%s]" % scope.rstrip("/") if scope else ""), system, counts["added"], counts["present"], counts["deleted"], counts["restored"],
        ", %d favourites imported" % imported if imported else ""))
    for w in warnings:
        emit("  WARN %s: %s -> %s" % (w["code"], w["path"], w["game"]))


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
