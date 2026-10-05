#!/usr/bin/env python3
"""
ps2hdd-hub.py -- drive the PS2 HDD when it is plugged into another machine (PS2_HDD_HOST, an
SSH alias: the Pi hub) instead of this Mac. Same commands as ps2hdd.py, no sudo here:

    python3 ps2hdd-hub.py status
    python3 ps2hdd-hub.py sync
    python3 ps2hdd-hub.py install [--dry-run] [--allow-same-id] [FILE ...] [--game NAME SOURCE ...]
    python3 ps2hdd-hub.py rename "OLD NAME" "NEW NAME"

This Mac sends the games; the host only writes them. install, one game at a time:
  - the source (a FILE under PS2_GAMES_PATH, a local path, or node:/path read over this
    Mac's SSH) is sent to the host's PS2_HDD_WORK_PATH/incoming (a .cue with its folder)
  - ps2hdd.py install runs there under sudo (deployed at /opt/cpc/ps2 by the Pi's ps2
    payload), with every check, the verify and the POST to Pluto
  - the sent copy is removed; a failed write stops the batch, like ps2hdd.py
At the end the header backups made on the host are moved to this Mac's
PS2_HDD_WORK_PATH/backups and the host's work dir is removed.

Pure stdlib, 3.6-safe, ASCII only.
"""
import os
import re
import subprocess
import sys

NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_SCRIPT = "/opt/cpc/ps2/scripts/ps2hdd.py"
REQUIRED = ["PS2_HDD_HOST", "PS2_GAMES_PATH", "PS2_HDD_WORK_PATH"]
REMOTE = re.compile(r"^([A-Za-z0-9_.-]+):(/.*)$")


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
        print("ps2hdd-hub: %s is missing required values:" % path)
        for k in missing:
            print("  - %s" % k)
        sys.exit(1)
    env["PS2_GAMES_PATH"] = os.path.expanduser(env["PS2_GAMES_PATH"])
    return env


def q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def run_remote(host, args):
    """ps2hdd.py on the host, output streamed here. -> (rc, saw a failed write)."""
    cmd = "sudo -n python3 -u %s %s" % (REMOTE_SCRIPT, " ".join(q(a) for a in args))
    p = subprocess.Popen(["ssh", host, cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stopped = False
    for raw in iter(p.stdout.readline, b""):
        line = raw.decode("ascii", "replace")
        sys.stdout.write(line)
        sys.stdout.flush()
        if line.startswith("Stopping here"):
            stopped = True
    return p.wait(), stopped


def send(host, source, dest):
    """A local path or node:/path -> dest on the host. -> the game's path there."""
    m = REMOTE.match(source)
    path = m.group(2) if m else source
    target = os.path.dirname(path) if path.lower().endswith(".cue") else path
    pack = "tar -C %s -cf - %s" % (q(os.path.dirname(target)), q(os.path.basename(target)))
    src = subprocess.Popen(["ssh", m.group(1), pack] if m else ["tar", "--no-xattrs", "--no-mac-metadata", "-C", os.path.dirname(target),
                                                                 "-cf", "-", os.path.basename(target)], stdout=subprocess.PIPE)
    put = subprocess.run(["ssh", host, "mkdir -p %s && tar -xf - -C %s" % (q(dest), q(dest))], stdin=src.stdout)
    src.stdout.close()
    if src.wait() != 0 or put.returncode != 0:
        return None
    there = os.path.join(dest, os.path.basename(target))
    return os.path.join(there, os.path.basename(path)) if target != path else there


def collect(env, host, work):
    """Header backups made on the host -> this Mac; then the host's work dir goes."""
    local = os.path.join(os.path.expanduser(env["PS2_HDD_WORK_PATH"]), "backups")
    if subprocess.call(["ssh", host, "test -d %s" % q(work + "/backups")]) == 0:
        if not os.path.isdir(local):
            os.makedirs(local)
        pack = subprocess.Popen(["ssh", host, "tar -C %s -cf - ." % q(work + "/backups")], stdout=subprocess.PIPE)
        unpack = subprocess.run(["tar", "-xf", "-", "-C", local], stdin=pack.stdout)
        pack.stdout.close()
        if pack.wait() != 0 or unpack.returncode != 0:
            print("Header backups could not be copied back: left on %s at %s/backups" % (host, work))
            return
        print("Header backups: %s" % local)
    # the work dir and any parents it needed (~/cpc/ps2): rmdir -p stops at the first non-empty one
    subprocess.call(["ssh", host, "rm -rf %s; rmdir -p %s 2>/dev/null; true" % (q(work), q(os.path.dirname(work)))])


def install(env, host, work, args):
    flags = [a for a in ("--dry-run", "--allow-same-id") if a in args]
    rest = [a for a in args if a not in flags]
    games, i = [], 0
    while i < len(rest):
        if rest[i] == "--game" and i + 2 < len(rest):
            games.append((rest[i + 1], rest[i + 2]))
            i += 3
        else:
            games.append((None, rest[i]))
            i += 1
    sources = []
    for name, source in games:
        if not REMOTE.match(source) and not os.path.isabs(source):
            source = os.path.join(env["PS2_GAMES_PATH"], source)
        sources.append((name, source))
    if "--dry-run" in flags:
        # the host plans from names only: a source here is node:/path to it (nothing is sent)
        argv = list(flags)
        for name, source in sources:
            there = source if REMOTE.match(source) else "mac:" + source
            argv += ["--game", name or os.path.splitext(os.path.basename(source))[0], there]
        return run_remote(host, ["install"] + argv)[0]
    failed = 0
    incoming = work + "/incoming"
    try:
        for name, source in sources:
            print("%s: sending to %s" % (name or os.path.basename(source), host))
            there = send(host, source, incoming)
            if not there:
                print("  FAILED: could not send %s" % source)
                failed += 1
                continue
            argv = flags + (["--game", name, there] if name else [there])
            rc, stopped = run_remote(host, ["install"] + argv)
            subprocess.call(["ssh", host, "rm -rf %s" % q(incoming)])
            failed += 1 if rc else 0
            if stopped:
                break
    finally:
        collect(env, host, work)
    return 1 if failed else 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("status", "sync", "install", "rename"):
        print(__doc__.strip().split("\n\n")[1])
        return 1
    env = load_env()
    host = env["PS2_HDD_HOST"]
    work = env["PS2_HDD_WORK_PATH"]
    if work.startswith("~"):
        home = subprocess.check_output(["ssh", host, "echo $HOME"]).decode("ascii").strip()
        work = home + work[1:]
    if sys.argv[1] == "install":
        return install(env, host, work, sys.argv[2:])
    return run_remote(host, sys.argv[1:])[0]


if __name__ == "__main__":
    sys.exit(main())
