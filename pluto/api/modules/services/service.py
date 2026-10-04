"""Per-node service control: what long-running units a node carries, and
start/stop/restart for each.

The list is declared BY THE NODE, in its own dir (nodes/local/<node>/services.json,
and pluto/services.json for the host) -- the same rule as .env, so adding a service
is an edit in that node's dir and never a change here. A node that declares nothing
simply has no services section.

Services are declared where they RUN, not where they are used: dreampi and openjvs
both live on the pi, so both are pi services.

An entry is an id and the systemd unit it names. Nothing describes what a service
does: systemd already holds that, and a second copy here would only go stale.

This module does no I/O of its own. It builds the shell one-liners and parses their
output; the caller supplies the SSH runner, so the same code works for any node.
"""

import json
import os

# systemctl verbs we expose. Anything else is rejected before it reaches a node.
OPS = ("start", "stop", "restart")


def services_path(base_dir, node_id):
    """Path to a node's services.json. Mirrors console_env_path: pluto is the host,
    so its list sits beside its own .env; every other node lives under nodes/local/."""
    if node_id == "pluto":
        return os.path.join(base_dir, "services.json")
    return os.path.normpath(os.path.join(base_dir, "..", "nodes", "local", node_id, "services.json"))


def load(base_dir, node_id):
    """-> list of declared services, or [] when the node declares none.

    A malformed file is treated as "none declared" rather than fatal: a typo in one
    node's list must not take the whole API down at startup."""
    path = services_path(base_dir, node_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    out = []
    for entry in (data.get("services") or []):
        unit = (entry.get("unit") or "").strip()
        sid = (entry.get("id") or "").strip()
        if not unit or not sid:
            continue
        out.append({"id": sid, "unit": unit})
    return out


def find(services, service_id):
    """-> the declared service with this id, or None. Callers must use this rather
    than trusting a request path: it is what keeps an arbitrary unit name off the
    systemctl command line."""
    for s in services:
        if s["id"] == service_id:
            return s
    return None


def status_argv(services):
    """argv asking a node for the state of every declared unit, one per line, in the
    declared order. `is-active` exits non-zero when anything is inactive, so the
    caller must read the output rather than the return code."""
    units = " ".join("'%s'" % s["unit"].replace("'", "") for s in services)
    return ["sh", "-c", "for u in %s; do printf '%%s %%s\\n' \"$u\" \"$(systemctl is-active \"$u\" 2>/dev/null || true)\"; done" % units]


def parse_status(services, out):
    """Merge `unit state` lines onto the declared services. A unit the node did not
    report back is 'unknown', which reads differently from 'inactive' on purpose:
    one means stopped, the other means we could not tell."""
    states = {}
    for line in (out or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            states[parts[0]] = parts[1]
    return [dict(s, state=states.get(s["unit"], "unknown")) for s in services]


def op_argv(service, op):
    """argv for one start/stop/restart. Root is required for all three; the nodes
    already allow passwordless sudo, which is how the SD and deploy paths work."""
    return ["sudo", "systemctl", op, service["unit"]]
