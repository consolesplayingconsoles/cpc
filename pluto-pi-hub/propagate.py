#!/usr/bin/env python3
"""
propagate.py -- the hub's next layer: flash each attached Pico with its role's
firmware, via mpremote. Ownership: role + firmware are CODE (firmware/<role>/);
the board->role binding is config you own (PICO_<chipid>=<role> in the node .env).

Identify boards by their real chip id (machine.unique_id() over the REPL), not the
spoofable USB serial. Idempotent + fault-tolerant. Run: python3 propagate.py <env>.
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
FW_ROOT = os.path.join(HERE, "firmware")
UID_PROBE = "import machine,binascii;print(binascii.hexlify(machine.unique_id()).decode())"


def _run(args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    out, _ = p.communicate()
    return p.returncode, out


def load_env(path):
    cfg = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip()
    return cfg


def parse_pico(value):
    """A PICO_<chipid> value -> a fields dict. Accepts the structured form
    'role=hid,conn=usb,managed=python' or the bare role shorthand 'hid'."""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1].strip()        # tolerate a quoted .env value
    if "=" not in value:
        return {"role": value} if value else {}
    out = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def attached_ports():
    _, out = _run(["mpremote", "devs"])
    return [ln.split()[0] for ln in out.splitlines()
            if ln.split() and ln.split()[0].startswith("/dev/")]


def board_uid(port):
    rc, out = _run(["mpremote", "connect", port, "exec", UID_PROBE])
    return out.strip().lower() if rc == 0 and out.strip() else None


def current_main(port):
    rc, out = _run(["mpremote", "connect", port, "cat", ":main.py"])
    return out if rc == 0 else None


def main(argv):
    env = load_env(argv[1] if len(argv) > 1 else "")
    want = {k[len("PICO_"):].lower(): parse_pico(v)
            for k, v in env.items() if k.startswith("PICO_")}
    if not want:
        print("propagate: no PICO_<chipid>=<role> binding -- nothing to flash")
        return 0
    ports = attached_ports()
    if not ports:
        print("propagate: no Picos attached -- nothing to flash")
        return 0
    for port in ports:
        uid = board_uid(port)
        if not uid:
            print("  [skip] %s: no chip id (busy? not MicroPython?)" % port)
            continue
        spec = want.get(uid)
        if not spec:
            print("  [skip] %s (%s): not in the .env binding" % (port, uid))
            continue
        role = spec.get("role")
        if not role:
            print("  [skip] %s (%s): no role in the .env binding" % (port, uid))
            continue
        # Pluto flashes a board IFF its role has firmware here. That existence IS the
        # pluto-vs-local deploy ownership -- the binding truth, no declarative flag to
        # drift out of sync (the dashboard derives the same way).
        fw = os.path.join(FW_ROOT, role, "main.py")
        if not os.path.exists(fw):
            print("  [skip] %s (%s): no firmware/%s/ -- deployed locally on the Pi, not by pluto" % (uid, role, role))
            continue
        with open(fw) as f:
            desired = f.read()
        print("##STEP:pico:%s" % role)
        if current_main(port) == desired:
            print("  [ok] %s (%s): already current" % (uid, role))
            continue
        print("  flashing %s (%s) on %s" % (uid, role, port))
        _run(["mpremote", "connect", port, "cp", fw, ":main.py"])
        _run(["mpremote", "connect", port, "reset"])
        print("  [done] %s (%s)" % (uid, role))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
