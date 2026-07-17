#!/usr/bin/env python3
"""Pre-commit guard: keep each non-Pluto API's OpenAPI spec in lockstep with the
routes its code actually exposes.

Bare stdlib http.server has no framework to generate the spec from, so a static
YAML would silently drift the moment someone adds/renames/removes an endpoint.
This fails the commit when a spec and its API's route table diverge. It does NOT
validate params or response schemas -- those stay hand-authored (low churn on
APIs this small).

Each API declares its routes as ONE literal that the dispatch also reads, so the
table can't drift from the code:
  ROUTES = {("GET","/health"): "_r_health", ...}    # dict, keys are (METHOD, path)
  SYNC_ROUTES = {("GET","/health"), ("POST","/sync")} # set of (METHOD, path)
We read that literal with `ast` (no import side effects) and the spec's paths +
methods with a tiny regex (no PyYAML dependency), then diff the two sets.

Exit 0 if every spec matches its code; 1 (with a report) otherwise.
"""
import ast
import os
import re
import sys

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

# (label, source file, route-constant name, openapi file) -- relative to repo root.
APIS = [
    ("translate",     "pluto-translate/cpc_translate_api.py", "ROUTES",      "pluto-translate/openapi.yaml"),
    ("pico-hub",      "pluto-pico-hub/hub.py",                 "SYNC_ROUTES", "pluto-pico-hub/openapi.yaml"),
    ("roomba-rally",  "nodes/local/roomba-rally/scripts/main.py",    "ROUTES",      "nodes/local/roomba-rally/openapi.yaml"),
    ("crazy-roomba",  "nodes/local/crazy-roomba/scripts/main.py", "ROUTES",    "nodes/local/crazy-roomba/openapi.yaml"),
    ("pluto",         "pluto/api/api.py",                      "API_ROUTES",  "pluto/api/openapi.yaml"),
    ("drive",         "pluto-drive/server.py",                 "ROUTES",      "pluto-drive/openapi.yaml"),
]


def code_routes(src_path, const):
    """(METHOD, path) set from the route-table literal, via ast (no import)."""
    tree = ast.parse(open(src_path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == const for t in node.targets):
            val = ast.literal_eval(node.value)
            items = val.keys() if isinstance(val, dict) else val
            return {(str(m).upper(), p) for (m, p) in items}
    raise SystemExit("  %s: route constant %s not found" % (src_path, const))


def spec_routes(spec_path):
    """(METHOD, path) set declared under `paths:` in an OpenAPI YAML."""
    routes = set()
    cur = None
    in_paths = False
    for line in open(spec_path):
        if re.match(r"^paths:\s*$", line):
            in_paths = True
            continue
        if in_paths and re.match(r"^\S", line):
            in_paths = False          # next top-level section ends paths:
        if not in_paths:
            continue
        m = re.match(r"^  (/\S*):\s*$", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^    ([a-z]+):", line)
        if m and m.group(1) in HTTP_METHODS and cur:
            routes.add((m.group(1).upper(), cur))
    return routes


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = False
    for label, src, const, spec in APIS:
        code = code_routes(os.path.join(root, src), const)
        doc = spec_routes(os.path.join(root, spec))
        only_code = code - doc
        only_spec = doc - code
        if only_code or only_spec:
            bad = True
            print("DRIFT  %s" % label)
            for m, p in sorted(only_code):
                print("  in code, missing from %s:  %s %s" % (spec, m, p))
            for m, p in sorted(only_spec):
                print("  in %s, missing from code:  %s %s" % (spec, m, p))
        else:
            print("ok     %-10s %d routes match %s" % (label, len(code), spec))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
