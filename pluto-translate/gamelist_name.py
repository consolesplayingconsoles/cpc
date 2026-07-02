#!/usr/bin/env python3
"""Give a translated build a DISTINCT display name in a system's gamelist.xml.

Batocera/EmulationStation identifies games by scraped metadata, not the filename, so a patch and
the original (same internal metadata) collapse to one entry and the dup is hidden. We override it:
write/refresh the <game> entry for the patch's ROM with a distinct <name>, so it lists as its own
game (e.g. a Catalan patch next to the Japanese original).

Console-AGNOSTIC: the ROM extension(s) are passed in, so this works for any system (.gdi, .chd,
.iso, .gba, ...), not just Dreamcast.

    gamelist_name.py <gamelist.xml> <sysdir> <dest-folder> <display-name> <rom-ext[,ext2,...]>

Pure stdlib (Batocera's minimal Python): no external deps.
"""
import sys, os, xml.etree.ElementTree as ET

gl, sysdir, dest, name, exts = sys.argv[1:6]
exts = tuple((e if e.startswith(".") else "." + e) for e in exts.lower().split(","))

rom = next((f for f in sorted(os.listdir(dest)) if f.lower().endswith(exts)), None)
if not rom:
    sys.exit("no %s in %s" % ("/".join(exts), dest))
rel = "./" + os.path.relpath(os.path.join(dest, rom), sysdir)

if os.path.exists(gl):
    root = ET.parse(gl).getroot()
else:
    root = ET.Element("gameList")

game = next((g for g in root.findall("game") if g.findtext("path") == rel), None)
if game is None:
    game = ET.SubElement(root, "game")
    ET.SubElement(game, "path").text = rel
n = game.find("name")
if n is None:
    n = ET.SubElement(game, "name")
n.text = name

ET.ElementTree(root).write(gl, encoding="utf-8", xml_declaration=True)
print("gamelist: %s -> %s" % (rel, name))
