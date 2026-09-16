#!/usr/bin/env python3
"""
ps2hdd.py -- install PS2 games from this Mac onto the PS2's internal HDD (APA format).

    sudo python3 ps2hdd.py status
    sudo python3 ps2hdd.py sync
    sudo python3 ps2hdd.py install [--dry-run] [--allow-same-id] FILE [FILE ...]
    sudo python3 ps2hdd.py rename "OLD NAME" "NEW NAME"

Pluto's Media tab hands out these commands: it can't read the raw disk itself. sync (and
every install, at the end) POSTs the drive's game list to Pluto (PLUTO_API), which merges
it into the catalogue like any sync: new games added, missing ones marked deleted.

FILE is a path under PS2_GAMES_PATH (absolute, or relative to it): .iso, .cue (+ .bin),
.chd, or a .7z/.zip holding one of those. sudo is needed to read/write the raw disk.

Every run checks the drive first and stops with an error when any check fails:
  - an external USB disk of exactly PS2_HDD_BYTES (pick with --disk diskN if several)
  - a PS2 APA header (APA + __mbr) in sector 0

install, per game:
  - named on the drive after its file (minus the extension), so the catalogue matches it
  - skipped when a game of that name is already on the drive, or one with the same disc ID
    (translations share it: --allow-same-id adds it anyway)
  - CD images (.cue/.bin, CD .chd) are converted to .iso in PS2_HDD_WORK_PATH/tmp
  - hdl_dump inject_cd / inject_dvd, then extract + byte compare against the source
Before the first write the APA partition headers are backed up to PS2_HDD_WORK_PATH/backups.
At the end the disk is flushed and ejected.

rename changes only a game's name on the drive (hdl_dump modify with a name, never flags or
-hide), e.g. to its full file name so the catalogue matches it to the other copies.

Only hdl_dump toc / hdl_toc / inject_cd / inject_dvd / extract / modify are ever run. Nothing is
deleted from the drive. An install interrupted mid-write (unplugged, killed) stays on the
drive under the game's name and later runs skip it: remove it on the PS2, then install again.

Pure stdlib, 3.6-safe, ASCII only.
"""
import argparse
import datetime
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request

NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ["PS2_GAMES_PATH", "PS2_HDD_BYTES", "PS2_HDD_WORK_PATH", "HDL_DUMP", "PLUTO_API"]
HDL_ALLOWED = {"toc", "hdl_toc", "inject_cd", "inject_dvd", "extract", "modify"}
NAME_MAX = 64                                   # hdl_dump HDL_GAME_NAME_MAX
GAME_EXTS = (".iso", ".cue", ".chd")
ARCHIVE_EXTS = (".7z", ".zip")


class Fail(Exception):
    """A clean, one-line error for the operator (and for Pluto's API later)."""


# --- config ---------------------------------------------------------------------------

def load_env():
    path = os.path.join(NODE_DIR, ".env")
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        print("ps2hdd: %s is missing required values:" % path)
        for k in missing:
            print("  - %s" % k)
        sys.exit(1)
    home = os.path.expanduser("~" + os.environ["SUDO_USER"]) if os.environ.get("SUDO_USER") else os.path.expanduser("~")
    for k in ("PS2_GAMES_PATH", "PS2_HDD_WORK_PATH", "HDL_DUMP"):
        if env[k].startswith("~"):
            env[k] = home + env[k][1:]
    try:
        env["PS2_HDD_BYTES"] = int(env["PS2_HDD_BYTES"])
    except ValueError:
        raise Fail("PS2_HDD_BYTES must be a number of bytes, got %r" % env["PS2_HDD_BYTES"])
    if not os.access(env["HDL_DUMP"], os.X_OK):
        raise Fail("hdl_dump not found at %s (run scripts/build-hdl-dump.sh)" % env["HDL_DUMP"])
    return env


def gb(n):
    return "%.1f GB" % (n / 1e9)


def as_user(path):
    """Files made under sudo go back to the operator, so later runs and Pluto can read them."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid and os.path.exists(path):
        os.chown(path, int(uid), int(gid))


def makedirs(path):
    if not os.path.isdir(path):
        os.makedirs(path)
        as_user(path)


# --- the drive ------------------------------------------------------------------------

def _plist(args):
    return plistlib.loads(subprocess.check_output(["diskutil", args[0], "-plist"] + args[1:]))


def find_drive(expected, disk=None):
    """-> {"disk": "disk6", "dev": "/dev/rdisk6"} after every safety check, else Fail."""
    if disk:
        names = [disk.replace("/dev/", "").replace("rdisk", "disk")]
    else:
        names = _plist(["list", "external", "physical"]).get("WholeDisks") or []
        if not names:
            raise Fail("No PS2 drive plugged in (no external disk found)")
    infos = [(n, _plist(["info", n])) for n in names]
    if not disk:
        sized = [(n, i) for n, i in infos if i.get("TotalSize", i.get("Size")) == expected]
        if not sized:
            raise Fail("No PS2 drive plugged in: external disk(s) %s, none is %s (PS2_HDD_BYTES)" % (
                ", ".join("%s %s" % (n, gb(i.get("TotalSize", i.get("Size", 0)))) for n, i in infos), gb(expected)))
        if len(sized) > 1:
            raise Fail("Several external disks of %s (%s): pick one with --disk" % (gb(expected), ", ".join(n for n, _ in sized)))
        infos = sized
    name, info = infos[0]
    size = info.get("TotalSize", info.get("Size"))
    if info.get("Internal", True):
        raise Fail("%s is an internal disk, refusing" % name)
    if info.get("BusProtocol") != "USB":
        raise Fail("%s is not a USB disk (%s), refusing" % (name, info.get("BusProtocol")))
    if not info.get("WholeDisk"):
        raise Fail("%s is a partition, not a whole disk, refusing" % name)
    if size != expected:
        raise Fail("%s is %s, expected %s (PS2_HDD_BYTES), refusing" % (name, gb(size), gb(expected)))
    dev = "/dev/r" + name
    try:
        with open(dev, "rb") as f:
            head = f.read(4096)
    except PermissionError:
        raise Fail("Can't read %s: run with sudo" % dev)
    if head[4:8] != b"APA\0" or head[0x10:0x15] != b"__mbr":
        raise Fail("%s is not a PS2 drive (no APA header), refusing" % name)
    return {"disk": name, "dev": dev}


def hdl(env, args, check=True):
    if args[0] not in HDL_ALLOWED:
        raise Fail("hdl_dump %s is not allowed" % args[0])
    p = subprocess.run([env["HDL_DUMP"]] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("ascii", "replace")
    if check and p.returncode != 0:
        raise Fail("hdl_dump %s failed: %s" % (args[0], " ".join(out.strip().splitlines()[-2:])))
    return p.returncode, out


def drive_games(env, drive):
    """-> ([{"type", "kb", "id", "name"}], free bytes) from hdl_toc."""
    _, out = hdl(env, ["hdl_toc", drive["dev"]])
    games, free = [], None
    for line in out.splitlines():
        m = re.match(r"^(CD|DVD)\s+(\d+)KB\s+\S+\s+\S+\s+(\S+)\s+(.*)$", line)
        if m:
            games.append({"type": m.group(1), "kb": int(m.group(2)), "id": m.group(3), "name": m.group(4).strip()})
        m = re.search(r"available\s+(\d+)MB", line)
        if m:
            free = int(m.group(1)) << 20
    if free is None:
        raise Fail("Could not read free space from hdl_toc")
    return games, free


def backup_headers(env, drive):
    """First 1MB of the disk + 8KB at every APA partition start, walked through the header
    chain (next pointer at 0x08). Index next to it records where each block came from."""
    out_dir = os.path.join(env["PS2_HDD_WORK_PATH"], "backups")
    makedirs(out_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    blob, index, lba, seen = bytearray(), [], 0, set()
    with open(drive["dev"], "rb") as f:
        f.seek(0)
        blob += f.read(1 << 20)
        index.append({"lba": 0, "bytes": 1 << 20})
        while lba not in seen:
            seen.add(lba)
            f.seek(lba * 512)
            h = f.read(8192)
            if h[4:8] != b"APA\0":
                raise Fail("Broken APA header chain at sector %d, not writing" % lba)
            blob += h
            index.append({"lba": lba, "bytes": 8192, "id": h[0x10:0x30].split(b"\0")[0].decode("ascii", "replace")})
            lba = struct.unpack_from("<I", h, 8)[0]
            if lba == 0:
                break
    base = os.path.join(out_dir, "%s-%s" % (stamp, drive["disk"]))
    with open(base + ".bin", "wb") as f:
        f.write(blob)
    with open(base + ".json", "w") as f:
        json.dump(index, f, indent=1)
    as_user(base + ".bin")
    as_user(base + ".json")
    return base + ".bin"


def eject(drive):
    subprocess.call(["sync"])
    if subprocess.call(["diskutil", "eject", drive["disk"]], stdout=subprocess.DEVNULL) != 0:
        raise Fail("Could not eject %s: do NOT unplug, run `diskutil eject %s`" % (drive["disk"], drive["disk"]))


# --- Pluto ----------------------------------------------------------------------------

def post_to_pluto(env, games):
    """The drive's complete game list -> the catalogue (system ps2, node ps2)."""
    files = [{"path": g["name"] + ".iso", "size": g["kb"] * 1024} for g in games]
    url = env["PLUTO_API"].rstrip("/") + "/catalogue/ps2/scan/ps2"
    req = urllib.request.Request(url, data=json.dumps({"files": files}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            lines = json.loads(r.read().decode("utf-8")).get("lines") or []
        print("Pluto: " + ("; ".join(lines) or "catalogue updated"))
    except urllib.error.HTTPError as e:
        print("Pluto did not take the game list (%s): run sync again later" % e.read().decode("utf-8", "replace").strip()[:200])
    except (urllib.error.URLError, OSError) as e:
        print("Pluto not reached at %s (%s): run sync again when it's up" % (env["PLUTO_API"], e))


# --- reading discs --------------------------------------------------------------------

def disc_id(read):
    """Startup ID (SLUS_204.39) from SYSTEM.CNF BOOT2. read(lba, count) -> 2048-byte sectors."""
    pvd = read(16, 1)
    if pvd[1:6] != b"CD001":
        return None
    lba, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    d = read(lba, (size + 2047) // 2048)
    i = 0
    while i < len(d):
        n = d[i]
        if n == 0:
            i = (i // 2048 + 1) * 2048
            continue
        name = d[i + 33:i + 33 + d[i + 32]]
        if name.upper().startswith(b"SYSTEM.CNF"):
            flba, fsize = struct.unpack_from("<I", d, i + 2)[0], struct.unpack_from("<I", d, i + 10)[0]
            cnf = read(flba, (fsize + 2047) // 2048)[:fsize].decode("ascii", "replace")
            m = re.search(r"BOOT2\s*=\s*cdrom0:\\?([^;\s]+)", cnf)
            return m.group(1) if m else None
        i += n
    return None


def cue_track(cue):
    """-> (bin path, sector size, data offset) for a single-track data CD, else Fail."""
    with open(cue, errors="replace") as f:
        text = f.read()
    files = re.findall(r'FILE\s+"([^"]+)"', text)
    tracks = re.findall(r"TRACK\s+\d+\s+(\S+)", text)
    if len(files) != 1 or len(tracks) != 1:
        raise Fail("%s: multi-track CD, not supported" % os.path.basename(cue))
    modes = {"MODE2/2352": (2352, 24), "MODE1/2352": (2352, 16), "MODE1/2048": (2048, 0)}
    if tracks[0] not in modes:
        raise Fail("%s: track mode %s not supported" % (os.path.basename(cue), tracks[0]))
    return (os.path.join(os.path.dirname(cue), files[0]),) + modes[tracks[0]]


def file_reader(path, sector=2048, offset=0):
    f = open(path, "rb")

    def read(lba, count):
        out = bytearray()
        for s in range(lba, lba + count):
            f.seek(s * sector + offset)
            out += f.read(2048)
        return bytes(out)
    return read


def stream_reader(argv, sector=2048, offset=0):
    """Forward-only sector reader over a process's stdout (7z e -so): bytes before the
    requested sectors are skipped, not kept, so SYSTEM.CNF deep in a padded ISO still works.
    Asking for a sector behind the read position raises EOFError."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pos = [0]

    def read(lba, count):
        start, end = lba * sector, (lba + count) * sector
        if start < pos[0]:
            raise EOFError
        while pos[0] < start:
            skipped = p.stdout.read(min(start - pos[0], 8 << 20))
            if not skipped:
                raise EOFError
            pos[0] += len(skipped)
        data = bytearray()
        while len(data) < end - start:
            chunk = p.stdout.read(end - start - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        pos[0] = end
        return b"".join(bytes(data[i + offset:i + offset + 2048]) for i in range(0, len(data), sector))
    return read, p


def archive_members(path):
    out = subprocess.check_output(["7z", "l", "-slt", "-ba", path]).decode("utf-8", "replace")
    members, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if cur.get("Path") and cur.get("Folder") != "+":
                members.append((cur["Path"], int(cur.get("Size") or 0)))
            cur = {}
        elif " = " in line:
            k, v = line.split(" = ", 1)
            cur[k] = v
    return members


def load_id_cache(env):
    """Disc IDs read out of archives, {source: {"stamp": "size:mtime", "id"}}: an archive
    is only decompressed for its ID once."""
    path = os.path.join(env["PS2_HDD_WORK_PATH"], "ids.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def save_id_cache(env, cache):
    makedirs(env["PS2_HDD_WORK_PATH"])
    path = os.path.join(env["PS2_HDD_WORK_PATH"], "ids.json")
    with open(path + ".tmp", "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)
    as_user(path)


def drive_name(filename):
    """Name on the drive: the file name without its extension, so the catalogue reads the
    drive copy exactly like the file it came from (regions, [T-En] translations)."""
    name = re.sub(r"\s+", " ", os.path.splitext(os.path.basename(filename))[0]).strip()
    if len(name) > NAME_MAX:
        name = name[:NAME_MAX].rsplit(" ", 1)[0].rstrip(" -")
    return name


def chd_kind(path):
    if not shutil.which("chdman"):
        raise Fail("%s needs chdman (brew install rom-tools)" % os.path.basename(path))
    info = subprocess.check_output(["chdman", "info", "-i", path]).decode("ascii", "replace")
    return "cd" if "CHT2" in info or "CHTR" in info else "dvd"


def describe(env, source):
    """What a source file is, without writing anything:
    {source, name, kind cd|dvd|?, id or None, iso_bytes (estimate), how}."""
    path = source if os.path.isabs(source) else os.path.join(env["PS2_GAMES_PATH"], source)
    if not os.path.isfile(path):
        raise Fail("No such file: %s" % path)
    rel = os.path.relpath(path, env["PS2_GAMES_PATH"])
    g = {"source": rel, "path": path, "name": drive_name(path), "id": None}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".iso":
        g.update(kind="dvd", iso_bytes=os.path.getsize(path), how="iso")
        g["id"] = disc_id(file_reader(path))
    elif ext == ".cue":
        bin_path, sector, offset = cue_track(path)
        g.update(kind="cd", iso_bytes=os.path.getsize(bin_path) // sector * 2048, how="cue")
        g["id"] = disc_id(file_reader(bin_path, sector, offset))
    elif ext == ".chd":
        info = subprocess.check_output(["chdman", "info", "-i", path]) if shutil.which("chdman") else b""
        m = re.search(rb"Logical size:\s+([\d,]+)", info)
        g.update(kind=chd_kind(path), iso_bytes=int(m.group(1).replace(b",", b"")) if m else 0, how="chd")
    elif ext in ARCHIVE_EXTS:
        members = archive_members(path)
        inner = [(p, s) for p, s in members if p.lower().endswith(GAME_EXTS)]
        if len(inner) != 1:
            raise Fail("%s: expected one .iso/.cue/.chd inside, found %d" % (os.path.basename(path), len(inner)))
        inner_path, inner_size = inner[0]
        g.update(how="archive", inner=inner_path)
        if inner_path.lower().endswith(".iso"):
            g.update(kind="dvd", iso_bytes=inner_size)
            read, p = stream_reader(["7z", "e", "-so", path, inner_path])
        elif inner_path.lower().endswith(".cue"):
            bins = [(q, s) for q, s in members if q.lower().endswith(".bin")]
            g.update(kind="cd", iso_bytes=sum(s for _, s in bins) // 2352 * 2048)
            read, p = stream_reader(["7z", "e", "-so", path, bins[0][0]], 2352, 24) if len(bins) == 1 else (None, None)
        else:
            g.update(kind="?", iso_bytes=inner_size)
            read, p = None, None
        stamp = "%d:%d" % (os.path.getsize(path), int(os.path.getmtime(path)))
        cache = load_id_cache(env)
        if cache.get(rel, {}).get("stamp") == stamp:
            g["id"] = cache[rel]["id"]
        elif read:
            try:
                g["id"] = disc_id(read)
            except EOFError:
                pass
            finally:
                p.kill()
                p.wait()
            cache[rel] = {"stamp": stamp, "id": g["id"]}
            save_id_cache(env, cache)
        elif p:
            p.kill()
            p.wait()
    else:
        raise Fail("%s: not a PS2 game file (.iso .cue .chd .7z .zip)" % os.path.basename(path))
    return g


# --- converting -----------------------------------------------------------------------

def to_iso(bin_path, sector, offset, out):
    with open(bin_path, "rb") as i, open(out, "wb") as o:
        while True:
            chunk = i.read(sector * 4096)
            if not chunk:
                break
            o.write(b"".join(chunk[s + offset:s + offset + 2048] for s in range(0, len(chunk) - sector + 1, sector)))


def prepare(env, g, tmp):
    """-> (iso path, kind) ready for inject, converting into tmp when needed."""
    path, how = g["path"], g["how"]
    if how == "archive":
        subprocess.check_call(["7z", "x", "-y", "-o" + tmp, path], stdout=subprocess.DEVNULL)
        path = os.path.join(tmp, g["inner"])
        how = os.path.splitext(path)[1].lower().lstrip(".")
    if how == "iso":
        return path, g["kind"]
    if how == "cue":
        bin_path, sector, offset = cue_track(path)
        if sector == 2048:
            return bin_path, "cd"
        out = os.path.join(tmp, "game.iso")
        to_iso(bin_path, sector, offset, out)
        return out, "cd"
    if how == "chd":
        kind = chd_kind(path)
        if kind == "dvd":
            out = os.path.join(tmp, "game.iso")
            subprocess.check_call(["chdman", "extractdvd", "-f", "-i", path, "-o", out], stdout=subprocess.DEVNULL)
            return out, "dvd"
        cue = os.path.join(tmp, "chd.cue")
        subprocess.check_call(["chdman", "extractcd", "-f", "-i", path, "-o", cue, "-ob", os.path.join(tmp, "chd.bin")], stdout=subprocess.DEVNULL)
        bin_path, sector, offset = cue_track(cue)
        out = os.path.join(tmp, "game.iso")
        to_iso(bin_path, sector, offset, out)
        return out, "cd"
    raise Fail("%s: don't know how to prepare" % g["source"])


def same_prefix(a, b, length):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        left = length
        while left:
            n = min(left, 8 << 20)
            if fa.read(n) != fb.read(n):
                return False
            left -= n
    return True


# --- commands -------------------------------------------------------------------------

def cmd_status(env, args):
    drive = find_drive(env["PS2_HDD_BYTES"], args.disk)
    games, free = drive_games(env, drive)
    print("Drive %s: PS2 APA, %s free, %d game(s)" % (drive["disk"], gb(free), len(games)))
    for x in games:
        print("  %-3s %-12s %s" % (x["type"], x["id"], x["name"]))


def cmd_sync(env, args):
    drive = find_drive(env["PS2_HDD_BYTES"], args.disk)
    games, free = drive_games(env, drive)
    print("Drive %s: PS2 APA, %s free, %d game(s)" % (drive["disk"], gb(free), len(games)))
    post_to_pluto(env, games)


def cmd_rename(env, args):
    new = re.sub(r"\s+", " ", args.new).strip()
    if not new or len(new) > NAME_MAX or new[0] in "+-*" or new.startswith("0x"):
        raise Fail("New name must be 1-%d characters and not start with + - * or 0x" % NAME_MAX)
    drive = find_drive(env["PS2_HDD_BYTES"], args.disk)
    names = [g["name"] for g in drive_games(env, drive)[0]]
    if args.old not in names:
        raise Fail("No game named '%s' on the drive" % args.old)
    if new in names:
        raise Fail("A game named '%s' is already on the drive" % new)
    try:
        hdl(env, ["modify", drive["dev"], args.old, new])
        subprocess.call(["sync"])
        games = drive_games(env, drive)[0]
        if new not in [g["name"] for g in games]:
            raise Fail("Renamed, but the drive doesn't list '%s': check with status" % new)
        print("Renamed '%s' -> '%s'" % (args.old, new))
        post_to_pluto(env, games)
    finally:
        eject(drive)
        print("Drive %s ejected: safe to unplug" % drive["disk"])


def plan(env, args, drive):
    games, free = drive_games(env, drive)
    on_drive = {x["name"]: x for x in games}
    by_id = {}
    for x in games:
        by_id.setdefault(x["id"], x)
    todo, skipped, names = [], [], set()
    for source in args.files:
        try:
            g = describe(env, source)
        except Fail as e:
            skipped.append((source, str(e)))
            continue
        if g["name"] in on_drive or g["name"] in names:
            skipped.append((g["source"], "a game named '%s' is already on the drive" % g["name"]))
            continue
        if g["id"] and g["id"] in by_id and not args.allow_same_id:
            skipped.append((g["source"], "disc ID %s already on drive as '%s' (--allow-same-id to add anyway)" % (g["id"], by_id[g["id"]]["name"])))
            continue
        names.add(g["name"])
        todo.append(g)
    need = sum(g["iso_bytes"] for g in todo)
    return todo, skipped, need, free


def cmd_install(env, args):
    drive = find_drive(env["PS2_HDD_BYTES"], args.disk)
    todo, skipped, need, free = plan(env, args, drive)
    print("Drive %s: PS2 APA, %s free" % (drive["disk"], gb(free)))
    for g in todo:
        print("  INSTALL %-3s %-12s %s  <- %s (%s)" % (g["kind"].upper(), g["id"] or "?", g["name"], g["source"], gb(g["iso_bytes"])))
    for source, why in skipped:
        print("  SKIP    %s: %s" % (source, why))
    print("Needs %s, %s free" % (gb(need), gb(free)))
    if need > free:
        raise Fail("Not enough space: needs %s, %s free" % (gb(need), gb(free)))
    if args.dry_run or not todo:
        return 0

    tmp = os.path.join(env["PS2_HDD_WORK_PATH"], "tmp")
    makedirs(env["PS2_HDD_WORK_PATH"])
    biggest = max(g["iso_bytes"] for g in todo)
    work_free = shutil.disk_usage(env["PS2_HDD_WORK_PATH"]).free
    if work_free < biggest * 2:
        raise Fail("Not enough space in %s for temp files: needs %s, %s free" % (env["PS2_HDD_WORK_PATH"], gb(biggest * 2), gb(work_free)))
    print("Header backup: %s" % backup_headers(env, drive))

    failed = 0
    try:
        for g in todo:
            shutil.rmtree(tmp, ignore_errors=True)
            makedirs(tmp)
            print("%s: preparing" % g["name"])
            try:
                iso, kind = prepare(env, g, tmp)
            except (Fail, subprocess.CalledProcessError) as e:
                print("  FAILED preparing: %s" % e)
                failed += 1
                continue
            print("%s: installing (%s)" % (g["name"], kind.upper()))
            rc, out = hdl(env, ["inject_" + kind, drive["dev"], g["name"], iso], check=False)
            if rc != 0:
                reason = " ".join(out.strip().splitlines()[-2:])
                print("  FAILED: %s" % reason)
                failed += 1
                continue
            subprocess.call(["sync"])
            check = os.path.join(tmp, "readback.iso")
            print("%s: verifying" % g["name"])
            rc, out = hdl(env, ["extract", drive["dev"], g["name"], check], check=False)
            size = os.path.getsize(iso)
            if rc == 0 and os.path.getsize(check) >= size and same_prefix(iso, check, size):
                print("  VERIFIED")
            else:
                print("  FAILED: read-back does not match the source")
                failed += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            post_to_pluto(env, drive_games(env, drive)[0])
        except Fail as e:
            print("Could not list the drive for Pluto (%s): run sync" % e)
        eject(drive)
        print("Drive %s ejected: safe to unplug" % drive["disk"])
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="Install PS2 games onto the PS2 HDD (APA).")
    ap.add_argument("--disk", help="the drive's diskN, when auto-detection finds several")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="check the drive and list its games")
    sub.add_parser("sync", help="send the drive's game list to Pluto's catalogue")
    r = sub.add_parser("rename", help="rename a game on the drive")
    r.add_argument("old")
    r.add_argument("new")
    p = sub.add_parser("install", help="install game files")
    p.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    p.add_argument("--allow-same-id", action="store_true", help="install even if the disc ID is already on the drive")
    p.add_argument("files", nargs="+")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1
    try:
        env = load_env()
        return {"status": cmd_status, "sync": cmd_sync, "install": cmd_install, "rename": cmd_rename}[args.cmd](env, args) or 0
    except Fail as e:
        print("ps2hdd: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
