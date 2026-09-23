#!/usr/bin/env python3
"""
names.py -- read a ROM filename into a title, its tags and its variants.

    Sonic the Hedgehog (USA, Europe) [T-Cat v0.6][Boss Versus v0.3].md
    '-- title ---------' '-- tags --' '-- variants -----------------'

  version     the game's own release version, split off the title so matching and
              cover lookup ignore it: TOSEC "Title v1.001 (2000)(Capcom)(US)" or a
              No-Intro tag "(Rev 1)" / "(Rev A)" / "(v1.1)". The tag stays in `tags`.
  (...)       tags, kept raw for display only. Regions come from the header, never
              from the name (headers.py): a filename can be wrong.
  [T-foo]     translation into foo. "[T-En by Some Team v1.0]" also carries its author,
              and so does a mod: "[Tokyo BS Guide by CPC v1.0]"
              (credited) and version.
  [anything]  a mod -- [!], [b], [h], [T+Eng] included. Cleanup happens by renaming.
  " vX.Y..."  a trailing version inside a bracket is split off, so "Boss Versus v0.3"
              and "Boss Versus v0.4" are the same mod.

Translation languages fold into config/languages.json codes: [T-Eng], [T-En] and
[T-English] are all "En"; [T-Cat] is "Ca". A variant keeps "lang" (the ISO code) for
linking to Translation projects. Other people's naming is tolerated: a language word left
outside the brackets ("Boku Doraemon (Japan) Catala [T-Cat] (v1.0)") is dropped from the
title, and a "(v1.0)" beside a translation is that translation's version.

`key()` is the grouping key used when a file has no header ID to match on.

Pure stdlib, 3.6-safe, ASCII only.
"""
import json
import os
import re
import unicodedata

_GENERIC_STEMS = {"disc", "disk", "game", "rom", "track01", "track1"}
_DOUBLE_EXT = re.compile(r"\.nkit$", re.I)     # Game.nkit.iso / Game.nkit.gcz
_TAG     = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")
_VERSION = re.compile(r"^(.*?)\s+v(\d[\w.\-]*)$", re.I)
_BY      = re.compile(r"^(.*?)\s+by\s+(.+)$", re.I)
_REV_TAG = re.compile(r"^(?:Rev\s+([\w.]+)|v(\d[\w.]*))$", re.I)


_REGION_WORDS = {"world", "usa", "europe", "japan", "asia", "korea", "china", "taiwan", "hong kong",
                 "brazil", "australia", "canada", "france", "germany", "spain", "italy", "netherlands",
                 "sweden", "uk", "russia", "portugal", "scandinavia", "latin america"}
_REGION_CODES = re.compile(r"^(?:[JUEWABKCFGSIH4]{1,3}|UK|Ch)$")


def same_title(a, b):
    """Two titles that are the same game spelled differently ("SOUKYU_GURENTAI" vs
    "Soukyuu Gurentai") as opposed to a hack under its own name ("Crazy Sonic")."""
    import difflib
    ka, kb = key(a), key(b)
    if ka == kb:
        return True
    wa, wb = ka.split("-"), kb.split("-")
    # Word by word: same word count, each word nearly identical (soukyu ~ soukyuu). A
    # character ratio over the whole title would pass "shadow-the-hedgehog" ~ "sonic-...".
    return len(wa) == len(wb) and all(difflib.SequenceMatcher(None, x, y).ratio() >= 0.75 for x, y in zip(wa, wb))


def has_region_tag(tags):
    """True when a name carries a No-Intro/GoodTools REGION tag like (USA, Europe) or (U).
    Only used to decide which dump of a game names it; badges still come from headers."""
    for t in tags:
        parts = [x.strip().lower() for x in t.split(",")]
        if all(x in _REGION_WORDS for x in parts) or _REGION_CODES.match(t.strip()):
            return True
    return False


_LANGS = None


def _languages():
    """{alias or code (folded, lowercase): code} from config/languages.json, loaded once."""
    global _LANGS
    if _LANGS is None:
        _LANGS = {}
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config", "languages.json")
        try:
            with open(p, encoding="utf-8") as f:
                for lang in json.load(f)["languages"]:
                    for a in [lang["code"], lang["label"]] + lang.get("aliases", []):
                        _LANGS[_fold(a)] = lang["code"]
        except (IOError, OSError, ValueError):
            pass
    return _LANGS


def _fold(text):
    """Lowercase, accents removed: "Català" -> "catala"."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower().strip()


def language_code(name):
    """ISO code for a translation tag's language ("Eng" -> "en"), or None if unknown."""
    return _languages().get(_fold(name))


def _split_version(text):
    m = _VERSION.match(text)
    return (m.group(1).strip(), m.group(2)) if m else (text, None)


def parse(filename):
    """-> {"title", "version", "tags", "variants": [{"kind", "name", "version"}]}."""
    stem = _DOUBLE_EXT.sub("", os.path.splitext(os.path.basename(filename))[0])
    # GDEMU-style dumps are "<Game folder>/disc.gdi": a generic file name says nothing, the folder does.
    if stem.lower() in _GENERIC_STEMS and os.path.dirname(filename):
        stem = os.path.basename(os.path.dirname(filename))
    tags, variants, version = [], [], None
    for m in _TAG.finditer(stem):
        paren, bracket = m.group(1), m.group(2)
        if paren is not None:
            tags.append(paren.strip())
            rev = _REV_TAG.match(paren.strip())
            if rev and version is None:
                version = rev.group(1) or rev.group(2)
            continue
        bracket = bracket.strip()
        if not bracket:
            continue
        kind = "translation" if bracket.startswith("T-") and len(bracket) > 2 else "mod"
        name, version = _split_version(bracket[2:] if kind == "translation" else bracket)
        v = {"kind": kind, "name": name, "version": version}
        by = _BY.match(name)          # mods carry an author the same way translations do
        if by:
            v["name"], v["author"] = by.group(1).strip(), by.group(2).strip()
        if kind == "translation":
            code = language_code(v["name"])
            if code:
                v["name"], v["lang"] = code.capitalize(), code
        variants.append(v)
    title = re.sub(r"\s+", " ", _TAG.sub(" ", stem)).strip()
    title, tosec = _split_version(title)
    translation = next((v for v in variants if v["kind"] == "translation"), None)
    if translation:
        # Tolerate names like "Game (Japan) Catala [T-Cat] (v1.0)": the stray language word
        # isn't part of the title, and the bare (v1.0) versions the translation, not the game.
        words = title.split(" ")
        while len(words) > 1 and language_code(words[-1]) and language_code(words[-1]) == translation.get("lang"):
            words.pop()
        title = " ".join(words)
        if version and not translation["version"]:
            translation["version"], version = version, None
    return {"title": title, "version": tosec or version, "tags": tags, "variants": variants}


def key(title):
    """'Legend of Zelda, The - A Link' -> 'the-legend-of-zelda-a-link'. Accents fold (a, not dropped)."""
    t = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c)).strip()
    m = re.match(r"^(.*?),\s*(The|A|An)\b(.*)$", t, re.I)
    if m:
        t = "%s %s%s" % (m.group(2), m.group(1), m.group(3))
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def variant_label(variants):
    """'original', 'T-Cat', 'Boss Versus', 'T-Cat + Boss Versus' (versions left out)."""
    parts = [("T-" if v["kind"] == "translation" else "") + v["name"] for v in variants]
    return " + ".join(parts) if parts else "original"


def canonical_name(title, file):
    """The name Pluto files a copy under when it writes one to a node: the game's title (its
    label when set), the copy's regions, its release version and its variants, in the same
    convention parse() reads back ("Title (Japan) (v1.1) [T-En by Team v1.0][Boss Versus v0.3]").
    Regions come from the header when there is one, else from the file's own region tags.
    No extension. parse(canonical_name(...) + ".iso") gives the same title/version/variants."""
    regions = list(file.get("regions") or []) or [t for t in file.get("tags") or [] if has_region_tag([t])]
    out = title.strip()
    if regions:
        out += " (%s)" % ", ".join(regions)
    # Release version only from the file's own (Rev x)/(vx) tag: parse() also reports a
    # variant's bracket version as `version`, which must not become the game's.
    rev = next((m for m in (_REV_TAG.match(t.strip()) for t in file.get("tags") or []) if m), None)
    if rev:
        out += " (%s)" % ("Rev " + rev.group(1) if rev.group(1) else "v" + rev.group(2))
    brackets = ""
    for v in file.get("variants") or []:
        inner = ("T-" if v["kind"] == "translation" else "") + v["name"]
        if v.get("author"):
            inner += " by " + v["author"]
        if v.get("version"):
            inner += " v" + v["version"]
        brackets += "[%s]" % inner
    if brackets:
        out += " " + brackets
    return re.sub(r"\s+", " ", out).strip()


def variant_key(game_key, v):
    """Composite key a mod/translation is indexed and credited by: game + name, no version."""
    return "%s/%s%s" % (game_key, "T-" if v["kind"] == "translation" else "", v["name"])
