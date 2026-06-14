#!/usr/bin/env python3
"""
gen_readme.py — regenerate the console table in the root README.

Scans the repo root for console node directories (any folder containing a
`.env.sample` that declares a real NODE_NAME + MANUFACTURER) and rewrites the
block between the CONSOLES markers in README.md. Adding or removing a console
folder is all it takes — the table maintains itself.

Usage:
    python3 scripts/gen_readme.py          # rewrite README.md in place
    python3 scripts/gen_readme.py --check   # exit 1 if README is stale (CI)

Stdlib only, Python 3.6+ compatible.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
START = "<!-- CONSOLES:START -->"
END = "<!-- CONSOLES:END -->"


def _parse_env(path):
    """Return a dict of KEY -> value from a .env-style file (quotes stripped)."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            out[k.strip()] = v
    return out


def discover_consoles():
    """Find console node dirs, sorted by folder name."""
    consoles = []
    for name in sorted(os.listdir(ROOT)):
        sample = os.path.join(ROOT, name, ".env.sample")
        if not os.path.isfile(sample):
            continue
        env = _parse_env(sample)
        node = env.get("NODE_NAME", "").strip()
        mfr = env.get("MANUFACTURER", "").strip()
        # A real console node declares both an identity and a manufacturer.
        # Infrastructure dirs (e.g. pluto) leave these blank and are skipped.
        if not node or not mfr:
            continue
        consoles.append({
            "folder": name,
            "node": node,
            "manufacturer": mfr,
        })
    return consoles


def build_table(consoles):
    rows = [
        "| Folder | Node | Manufacturer |",
        "|--------|------|--------------|",
    ]
    for c in consoles:
        node = c["node"]
        if c["description"]:
            node = "{} — {}".format(node, c["description"])
        rows.append("| [{f}/](./{f}/) | {n} | {m} |".format(
            f=c["folder"], n=node, m=c["manufacturer"]))
    return "\n".join(rows)


def render(readme_text, table):
    if START not in readme_text or END not in readme_text:
        sys.stderr.write(
            "ERROR: README.md is missing the {s} / {e} markers.\n".format(
                s=START, e=END))
        sys.exit(2)
    head, _, rest = readme_text.partition(START)
    _, _, tail = rest.partition(END)
    return "{head}{start}\n{table}\n{end}{tail}".format(
        head=head, start=START, table=table, end=END, tail=tail)


def main():
    check = "--check" in sys.argv[1:]
    with open(README) as f:
        current = f.read()
    consoles = discover_consoles()
    updated = render(current, build_table(consoles))

    if check:
        if updated != current:
            sys.stderr.write(
                "README console table is stale. Run: python3 scripts/gen_readme.py\n")
            sys.exit(1)
        print("README console table is up to date ({} nodes).".format(len(consoles)))
        return

    if updated != current:
        with open(README, "w") as f:
            f.write(updated)
        print("Regenerated console table ({} nodes).".format(len(consoles)))
    else:
        print("README already up to date ({} nodes).".format(len(consoles)))


if __name__ == "__main__":
    main()
