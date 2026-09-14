#!/usr/bin/env python3
"""
gamelist.py -- read Batocera's /userdata/roms/<system>/gamelist.xml.

    <gameList>
      <game>
        <path>./Sonic the Hedgehog (USA, Europe).md</path>
        <name>Sonic The Hedgehog</name>
        <image>./images/Sonic the Hedgehog (USA, Europe)-image.png</image>
        <thumbnail>./images/Sonic the Hedgehog (USA, Europe)-thumb.png</thumbnail>
        <favorite>true</favorite>
      </game>
    </gameList>

Used for two things only: scraped cover paths (first choice for covers) and a ONE-TIME
favourites import. Batocera's gamelist is never written and never the source of truth.
Paths come back relative to the system dir, matching scan.py ("./" stripped).

Pure stdlib, 3.6-safe, ASCII only.
"""
import os
import xml.etree.ElementTree as ET


def _rel(p):
    p = (p or "").strip()
    return os.path.normpath(p[2:] if p.startswith("./") else p) if p else None


def parse(xml_text):
    """-> {rel path: {"name", "image", "thumbnail", "favorite"}}. Empty/broken xml -> {}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}
    out = {}
    for g in root.iter("game"):
        path = _rel(g.findtext("path"))
        if not path:
            continue
        out[path] = {
            "name":      (g.findtext("name") or "").strip() or None,
            "image":     _rel(g.findtext("image")),
            "thumbnail": _rel(g.findtext("thumbnail")),
            "favorite":  (g.findtext("favorite") or "").strip().lower() == "true",
        }
    return out
