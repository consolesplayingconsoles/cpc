#!/usr/bin/env python3
"""Reproducible text-compression pipeline for a translation, driven through the Pluto API.

The mechanical byte-shaving passes that turn a raw extract into the compressed state
(ellipsis/bang tidy, de-stutter, the menu-button and dorayaki phrase rules, Gràcies->Merci,
terminal-period drop). Runs GET -> transform -> PUT against `pluto/api`, so the path from
extraction to today's state is auditable and re-runnable instead of living in scratch scripts.
It is idempotent: on an already-compressed state it reports zero changes.

CONTENT decisions (the per-line rewordings, the terse room nouns, the scene trims) are NOT
here -- those are the translator's choices and live in the state itself. This captures only
the rule-based layer. Glyph encoding (contractions, digraphs, faces) is build-time in fon_codec.

    compress.py <game> [api_base]          # default api_base http://localhost:7700
    compress.py "Boku Doraemon (Japan) [ca]" --dry      # report only, no PUT
"""
import sys, re, json, urllib.parse, urllib.request

# ── generic Catalan/text tidy (reusable across games) ──────────────────────────
_STUT = re.compile(r"((?:[A-Za-zÀ-ÿ]{1,4}(?:…|\.\.\.)[ ]*)+)([A-Za-zÀ-ÿ]{3,})")
def _destutter(ca):
    def f(m):
        fr = re.findall(r"([A-Za-zÀ-ÿ]{1,4})(?:…|\.\.\.)", m.group(1)); w = m.group(2)
        if fr and all(w.lower().startswith(x.lower()) for x in fr):
            return (w[0].upper() + w[1:]) if fr[0][:1].isupper() else w
        return m.group(0)
    return _STUT.sub(f, ca)
def _de_elong(ca):
    def r(m):
        ch = m.group(1); i = m.start(); prev = ca[i-1] if i > 0 else ""
        return ch.lower() if (ch.isupper() and prev.isalpha() and prev.islower()) else ch
    return re.sub(r"([A-Za-zÀ-ÿ])\1{2,}", r, ca)
def tidy(ca):
    ca = _destutter(ca)
    ca = _de_elong(ca)
    ca = ca.replace("...", "…")          # the JP's own single ellipsis glyph (6B -> 2B)
    ca = re.sub(r"!{2,}", "!", ca)        # collapse !! / !!! (keep ?! / !?)
    return ca

# ── Boku Doraemon specific rule passes (the franchise/game layer) ──────────────
def menu(ca):
    return (ca.replace("Botó A: sí. Botó B: no.", "A:sí B:no")
              .replace("Botó A", "A").replace("Botó B", "B"))
def dorayaki(ca):
    return ca.replace("pastissets de melmelada", "pastissets").replace("pastisset de melmelada", "pastisset")
def merci(ca):
    return ca.replace("Gràcies", "Merci")
def period(ca):
    c = ca.rstrip()
    return c[:-1] if (c.endswith(".") and not c.endswith("…")) else ca

PASSES = [tidy, menu, dorayaki, merci, period]

# ── Pluto API (the reproducible channel) ───────────────────────────────────────
def _url(base, game):
    return base.rstrip("/") + "/translate/" + urllib.parse.quote(game)
def api_get(base, game):
    with urllib.request.urlopen(_url(base, game), timeout=30) as r:
        return json.load(r)
def api_put(base, game, sources):
    body = json.dumps({"sources": sources}).encode("utf-8")
    req = urllib.request.Request(_url(base, game), data=body, method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status
def api_measure(base, game, path, file, blocks):
    body = json.dumps({"blocks": [{"offset": b.get("offset"), "ca": b.get("ca"), "jpBytes": b.get("jpBytes")}
                                  for b in blocks]}).encode("utf-8")
    u = (base.rstrip("/") + "/translate/measure?path=" + urllib.parse.quote(path)
         + "&file=" + urllib.parse.quote(file))
    req = urllib.request.Request(u, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("used", {})
def _overflow(used, budget):
    def slack(s):
        if isinstance(budget, dict): return budget.get(str(s), budget.get(s, 0)) or 0
        return budget[s] if (isinstance(budget, list) and s < len(budget)) else 0
    over = sum(max(0, v - slack(int(k))) for k, v in used.items())
    nover = sum(1 for k, v in used.items() if v > slack(int(k)))
    return over, nover


def main():
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv
    if not args:
        print("usage: compress.py <game> [api_base] [--dry]"); sys.exit(1)
    game = args[0]
    base = args[1] if len(args) > 1 else "http://localhost:7700"
    state = api_get(base, game)
    changed = {}
    for name, blocks in (state.get("sources") or {}).items():
        n = 0
        for b in blocks:
            if b.get("done"):
                continue
            ca = b.get("ca") or ""
            new = ca
            for p in PASSES:
                new = p(new)
            if new != ca:
                b["ca"] = new; n += 1
        if n:
            changed[name] = blocks
            print("  %-20s %d lines changed" % (name, n))
    if not changed:
        print("idempotent: state already compressed, nothing to PUT")
    elif dry:
        print("--dry: %d sources would change (no PUT)" % len(changed))
    else:
        api_put(base, game, changed)
        print("PUT via Pluto API: %d sources saved" % len(changed))
    # report overflow through the /measure API (reproducible measure channel), STORY.PAC
    budget = (state.get("sceneBudget") or {}).get("STORY.PAC")
    sp = (state.get("sources") or {}).get("STORY.PAC")
    if budget is not None and sp is not None:
        used = api_measure(base, game, state.get("path"), "STORY.PAC", sp)
        over, nover = _overflow(used, budget)
        print("overflow (via /measure API): %d B over %d scenes" % (over, nover))


if __name__ == "__main__":
    main()
