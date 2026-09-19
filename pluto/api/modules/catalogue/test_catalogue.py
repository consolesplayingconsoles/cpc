#!/usr/bin/env python3
"""Unit tests for the catalogue matcher: names, headers, merge.

The risk worth testing is silent mis-grouping: a mod filed as its own game, two
regions split apart, or a failed read wiping a node's list. Headers are synthesised
here rather than committed as ROM fixtures.

    python3 test_catalogue.py     # plain asserts, no pytest
"""
import json
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamelist
import covers
import headers
import metadata
import names
import scan
import send
import service
import shutil
import store
import subprocess

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

NOW, LATER = "2026-09-14T10:00:00", "2026-09-15T10:00:00"


# -- names -------------------------------------------------------------------

def test_plain_no_intro_name():
    p = names.parse("roms/megadrive/Sonic the Hedgehog (USA, Europe).md")
    assert p == {"title": "Sonic the Hedgehog", "version": None, "tags": ["USA, Europe"], "variants": []}
    assert names.variant_label(p["variants"]) == "original"


def test_translation_and_versioned_mod():
    p = names.parse("Sonic the Hedgehog (Europe) [T-Cat v0.6-Beta][Boss Versus v0.3].md")
    assert p["variants"] == [{"kind": "translation", "name": "Ca", "version": "0.6-Beta", "lang": "ca"},
                             {"kind": "mod", "name": "Boss Versus", "version": "0.3"}]
    assert names.variant_label(p["variants"]) == "T-Ca + Boss Versus"
    assert names.variant_key("sonic-the-hedgehog", p["variants"][1]) == "sonic-the-hedgehog/Boss Versus"


def test_translation_by_author_is_credited():
    p = names.parse("Mother 3 (Japan) [T-En by Chewy & Jeffman & Tomato v1.3].zip")
    assert p["variants"] == [{"kind": "translation", "name": "En", "version": "1.3", "author": "Chewy & Jeffman & Tomato", "lang": "en"}]


def test_language_synonyms_and_stray_language_words():
    ca = names.parse("Boku Doraemon (Japan) Català [T-Cat] (v1.0)/Boku Doraemon (Japan) Català [T-Cat] (v1.0).gdi")
    en = names.parse("Boku Doraemon (Japan) English [T-Eng] (v1.0).gdi")
    assert ca["title"] == en["title"] == "Boku Doraemon"
    assert ca["variants"] == [{"kind": "translation", "name": "Ca", "version": "1.0", "lang": "ca"}] and ca["version"] is None
    assert names.variant_label(en["variants"]) == names.variant_label(names.parse("Boku Doraemon (Japan) [T-En].gdi")["variants"]) == "T-En"
    assert names.key("Pokémon") == "pokemon"
    assert names.parse("Street Fighter (Japan) [T-Klingon v1].zip")["variants"][0]["name"] == "Klingon"   # unknown: kept


def test_every_other_bracket_is_a_mod():
    p = names.parse("Phantasy Star II (J) [!] [T+Eng] [b1] [h].bin")
    assert [v["name"] for v in p["variants"]] == ["!", "T+Eng", "b1", "h"]
    assert all(v["kind"] == "mod" for v in p["variants"])


def test_release_version_is_split_off_the_title():
    tosec = names.parse("Cannon Spike v1.001 (2000)(Capcom)(US)[!].zip")
    assert tosec["title"] == "Cannon Spike" and tosec["version"] == "1.001"
    assert names.parse("Dreamkey 3.1 v1.000 (2002)(Sega)(PAL)(ES)[!].zip")["title"] == "Dreamkey 3.1"
    rev = names.parse("Grand Theft Auto 2 (Europe) (EnFrDeEsIt) (Rev 1).cue")
    assert rev["title"] == "Grand Theft Auto 2" and rev["version"] == "1" and "Rev 1" in rev["tags"]
    assert names.parse("Game (USA) (v1.1).gba")["version"] == "1.1"
    assert names.parse("Street Fighter III 3rd Strike (Japan).cdi")["version"] is None


def test_generic_file_name_uses_the_folder():
    p = names.parse("SGGG - Segagaga v1.022 (JP) [ENG]/disc.gdi")
    assert p["title"] == "SGGG - Segagaga" and p["version"] == "1.022"


def test_nkit_double_extension():
    assert names.parse("Super Mario Sunshine (USA).nkit.iso")["title"] == "Super Mario Sunshine"


def test_key_matches_the_frontend_mirror():
    """Same cases as src/lib/catalogueNames.test.ts: change one side, change both."""
    assert names.key("Legend of Zelda, The - A Link to the Past") == "the-legend-of-zelda-a-link-to-the-past"
    assert names.key("L.O.L. - Lack of Love") == "l-o-l-lack-of-love"
    assert names.key("Pokémon Català") == "pokemon-catala"


def test_key_folds_trailing_article():
    assert names.key("Legend of Zelda, The - A Link to the Past") == \
        names.key("The Legend of Zelda: A Link to the Past")


def test_canonical_name_round_trips_through_parse():
    for path in ("Sonic the Hedgehog (Europe) [T-Cat v0.6-Beta][Boss Versus v0.3].md",
                 "Mother 3 (Japan) [T-En by Chewy & Jeffman & Tomato v1.3].zip",
                 "Game (USA) (v1.1).gba", "Kunoichi (Japan).7z"):
        p = names.parse(path)
        f = {"regions": [], "tags": p["tags"], "version": p["version"], "variants": p["variants"]}
        back = names.parse(names.canonical_name(p["title"], f) + ".iso")
        assert (back["title"], back["variants"]) == (p["title"], p["variants"]), (path, back)
    assert names.canonical_name("Game", {"tags": ["USA", "v1.1"], "variants": []}) == "Game (USA) (v1.1)"
    assert names.canonical_name("Game", {"tags": ["Rev 1"], "variants": [{"kind": "mod", "name": "Hack", "version": "2"}]}) == "Game (Rev 1) [Hack v2]"
    p = names.parse("Front Mission 5 - Scars of the War (Patch 4 Complete)(Translated OP addendum).7z")
    f = {"regions": ["Japan"], "tags": p["tags"], "version": None, "variants": []}
    assert names.canonical_name("Front Mission 5 - Scars of the War", f) == "Front Mission 5 - Scars of the War (Japan)"


# -- headers -----------------------------------------------------------------

def md_rom(serial, title, region=b"JUE"):
    h = bytearray(0x200)
    h[0x100:0x110] = b"SEGA MEGA DRIVE "
    h[0x150:0x150 + len(title)] = title
    h[0x180:0x18E] = serial
    h[0x1F0:0x1F0 + len(region)] = region
    return bytes(h)


def test_megadrive_header():
    got = headers.read("megadrive", md_rom(b"GM 00001009-00", b"SONIC THE HEDGEHOG"))
    assert got == {"id": "GM 00001009-00", "title": "SONIC THE HEDGEHOG", "regions": ["Japan", "USA", "Europe"]}


def test_megadrive_hex_region_and_letter_e():
    assert headers.read("megadrive", md_rom(b"GM T-00000-00", b"X", b"8"))["regions"] == ["Europe"]
    assert headers.read("megadrive", md_rom(b"GM T-00000-00", b"X", b"E"))["regions"] == ["Europe"]
    assert headers.read("megadrive", md_rom(b"GM T-00000-00", b"X", b"5"))["regions"] == ["Japan", "USA"]


def test_gba_header():
    h = bytearray(0xC0)
    h[0xA0:0xAC] = b"POKEMON EMER"
    h[0xAC:0xB0] = b"BPEE"
    assert headers.read("gba", h) == {"id": "BPEE", "title": "POKEMON EMER", "regions": ["USA"]}


def test_sms_product_code_bcd():
    h = bytearray(0x8000)
    h[0x7FF0:0x7FF8] = b"TMR SEGA"
    h[0x7FFC], h[0x7FFD], h[0x7FFE], h[0x7FFF] = 0x05, 0x70, 0x40, 0x4C   # 47005, export
    assert headers.read("sms", h) == {"id": "47005", "title": "", "regions": ["Export"]}


def ipbin(magic, id_off, pid, title_off, title, raw, area_off, area):
    s = bytearray(0x200)
    s[0:16] = magic
    s[area_off:area_off + len(area)] = area
    s[id_off:id_off + 10] = pid.ljust(10)
    s[title_off:title_off + len(title)] = title
    return bytes(bytearray(0x10) + s) if raw else bytes(s)


def test_disc_ipbin_cooked_and_raw():
    for raw in (False, True):
        sat = ipbin(b"SEGA SEGASATURN ", 0x20, b"GS-9170", 0x60, b"NIGHTS", raw, 0x40, b"JTUE")
        assert headers.read("saturn", sat) == {"id": "GS-9170", "title": "NIGHTS",
                                               "regions": ["Japan", "Asia", "USA", "Europe"]}
        dc = ipbin(b"SEGA SEGAKATANA ", 0x40, b"HDR-0073", 0x80, b"SHENMUE", raw, 0x30, b"J  ")
        assert headers.read("dreamcast", dc) == {"id": "HDR-0073", "title": "SHENMUE", "regions": ["Japan"]}


def test_real_config_formats_are_all_known():
    with open(os.path.join(FIXTURES, "..", "..", "..", "..", "config", "consoles.json")) as f:
        cfg = json.load(f)
    fmts = service.header_formats(cfg)
    assert fmts["mastersystem"] == fmts["gamegear"] == "sms"
    assert all(headers.read(fmt, b"") is None and fmt in headers._READERS for fmt in fmts.values())


def test_no_header_means_name_match():
    assert headers.read("megadrive", b"\x00" * 0x200) is None
    assert headers.read(None, b"\x00" * 0x200) is None


# -- merge -------------------------------------------------------------------

SONIC_H = {"id": "GM 00001009-00", "title": "SONIC THE HEDGEHOG", "regions": ["Japan", "USA", "Europe"]}


def test_mod_with_base_header_joins_base_game():
    doc = store.empty("megadrive")
    _, warn, _ = store.merge(doc, "batocera", [
        {"path": "Sonic the Hedgehog (USA, Europe).md", "header": SONIC_H},
        {"path": "Sonic 1 Boss Mod [Boss Versus].md",   "header": SONIC_H},
    ], NOW)
    assert list(doc["games"]) == ["sonic-the-hedgehog"]
    assert [w["code"] for w in warn] == ["id-name-mismatch"]
    assert sorted(store.variants(doc["games"]["sonic-the-hedgehog"])) == ["Boss Versus", "original"]


def test_placeholder_header_id_shared_by_two_dumps_is_ignored():
    """A pre-loaded card's junk ID (00000 on 16 Master System games) must not group them."""
    doc = store.empty("mastersystem")
    counts, _, _ = store.merge(doc, "sms", [
        {"path": "Altered Beast (USA, Europe).sms", "header": {"id": "00000", "title": "", "regions": []}},
        {"path": "Bomber Raid (World).sms", "header": {"id": "00000", "title": "", "regions": []}},
        {"path": "Micro Machines (Europe).sms", "header": {"id": "00000", "title": "", "regions": []}},
    ], NOW)
    assert counts["added"] == 3
    assert sorted(doc["games"]) == ["altered-beast", "bomber-raid", "micro-machines"]
    assert all(not g["ids"] for g in doc["games"].values())


def test_one_id_two_region_dumps_of_the_same_game_still_groups():
    doc = store.empty("mastersystem")
    store.merge(doc, "sms", [
        {"path": "Fantasy Zone (World) (v1.2).sms", "header": {"id": "05110", "title": "", "regions": []}},
        {"path": "Fantasy Zone (Japan).sms", "header": {"id": "05110", "title": "", "regions": []}},
    ], NOW)
    assert list(doc["games"]) == ["fantasy-zone"]
    assert doc["games"]["fantasy-zone"]["ids"] == ["05110"]


def test_strip_cuts_a_cards_number_prefix_off_the_title_only():
    """The EverDrive card numbers its games: the path stays, the title loses the number."""
    doc = store.empty("mastersystem")
    store.merge(doc, "sms", [
        {"path": "ROM A-Z/157 Golden Axe Warrior (USA, Europe).sms", "header": None},
        {"path": "ROM- SG1000 SC3000/007 James Bond (Japan).sg", "header": None},
    ], NOW, strip=r"(?<=ROM A-Z/)[0-9]{3}\s")
    # folder-scoped: the numbered card folder loses its number, a game that really starts
    # with digits, in another folder, keeps them
    assert sorted(doc["games"]) == ["007-james-bond", "golden-axe-warrior"]
    f = doc["games"]["golden-axe-warrior"]["files"][0]
    assert f["path"] == "ROM A-Z/157 Golden Axe Warrior (USA, Europe).sms"
    assert f["tags"] == ["USA, Europe"]


def test_unbracketed_hack_is_a_mod_and_does_not_name_the_game():
    doc = store.empty("megadrive")
    _, warn, _ = store.merge(doc, "batocera", [
        {"path": "Crazy Sonic.zip", "header": SONIC_H},
        {"path": "Shadow The Hedgehog (S1 Hack).bin", "header": SONIC_H},
        {"path": "Sonic The Hedgehog (USA, Europe).zip", "header": SONIC_H},
        {"path": "Sonic The Hedgehog (Japan, Korea).zip", "header": SONIC_H},
        {"path": "Sonic the Hedgehog.bin", "header": SONIC_H},
    ], NOW)
    assert list(doc["games"]) == ["sonic-the-hedgehog"]
    by = {f["path"]: names.variant_label(f["variants"]) for f in doc["games"]["sonic-the-hedgehog"]["files"]}
    assert by["Crazy Sonic.zip"] == "Crazy Sonic" and by["Sonic The Hedgehog (Japan, Korea).zip"] == "original"
    assert by["Sonic the Hedgehog.bin"] == "original" and by["Shadow The Hedgehog (S1 Hack).bin"] == "Shadow The Hedgehog"
    assert sorted(w["code"] for w in warn) == ["unbracketed-mod", "unbracketed-mod"]


def test_region_named_dump_from_a_later_scan_takes_the_game_over():
    doc = store.empty("saturn")
    h = {"id": "T-1805G", "title": "SOUKYU GURENTAI", "regions": ["Japan"]}
    store.merge(doc, "batocera", [{"path": "Soukyuu Gurentai (Japan)/SOUKYU_GURENTAI.cue", "header": h}], NOW)
    assert list(doc["games"]) == ["soukyu-gurentai"]
    _, warn, renames = store.merge(doc, "lab", [{"path": "Soukyuu Gurentai (Japan)/Soukyuu Gurentai (Japan).cue", "header": h}], LATER)
    assert list(doc["games"]) == ["soukyuu-gurentai"] and renames == {"soukyu-gurentai": "soukyuu-gurentai"}
    by = {f["node"]: names.variant_label(f["variants"]) for f in doc["games"]["soukyuu-gurentai"]["files"]}
    assert by == {"lab": "original", "batocera": "original"}          # same game, badly named: not a mod
    assert names.same_title("SOUKYU_GURENTAI", "Soukyuu Gurentai") and not names.same_title("Crazy Sonic", "Sonic The Hedgehog")


def test_reused_product_id_with_a_different_header_title_is_another_game():
    doc = store.empty("saturn")
    store.merge(doc, "batocera", [
        {"path": "Virtua Fighter 2 (Japan)/Virtua Fighter 2 (Japan).cue", "header": {"id": "GS-9079", "title": "VIRTUA FIGHTER 2", "regions": ["Japan"]}},
        {"path": "Virtua Fighter Kids (Japan)/Virtua Fighter Kids (Japan).cue", "header": {"id": "GS-9079", "title": "VF. KIDS", "regions": ["Japan"]}},
    ], NOW)
    assert sorted(doc["games"]) == ["virtua-fighter-2", "virtua-fighter-kids"]


def test_name_fallback_joins_across_nodes():
    doc = store.empty("megadrive")
    store.merge(doc, "batocera",  [{"path": "Sonic the Hedgehog (USA, Europe).md", "header": SONIC_H}], NOW)
    store.merge(doc, "megadrive", [{"path": "Sonic the Hedgehog (Japan).chd",      "header": None}], NOW)
    g = doc["games"]["sonic-the-hedgehog"]
    assert sorted(f["node"] for f in g["files"]) == ["batocera", "megadrive"]
    assert [f["regions"] for f in g["files"]] == [["Japan", "USA", "Europe"], []]   # none from the name


def test_variant_with_no_base_warns():
    doc = store.empty("megadrive")
    _, warn, _ = store.merge(doc, "batocera", [{"path": "Sonic Boss Rush [Boss Versus].md", "header": None}], NOW)
    assert [w["code"] for w in warn] == ["new-game-variant"]
    _, warn, _ = store.merge(doc, "batocera", [{"path": "Sonic Boss Rush [Boss Versus].md", "header": None}], LATER)
    assert warn == []


def test_first_original_retitles_and_rekeys_a_mod_only_game():
    doc = store.empty("megadrive")
    store.merge(doc, "megadrive", [{"path": "Sonic 1 Boss Mod [Boss Versus].md", "header": SONIC_H}], NOW)
    assert list(doc["games"]) == ["sonic-1-boss-mod"]
    favs = {"games": {"megadrive": ["sonic-1-boss-mod"]}, "imported": {}}
    credits = {"sonic-1-boss-mod/Boss Versus": {"author": "francesc"}}

    _, warn, renames = store.merge(doc, "batocera", [{"path": "Sonic the Hedgehog (Japan).md", "header": SONIC_H}], LATER)
    assert renames == {"sonic-1-boss-mod": "sonic-the-hedgehog"}
    assert [w["code"] for w in warn] == ["game-rekeyed"]
    g = doc["games"]["sonic-the-hedgehog"]
    assert g["title"] == "Sonic the Hedgehog" and len(g["files"]) == 2 and list(doc["games"]) == ["sonic-the-hedgehog"]

    store.rekey_refs(favs, credits, "megadrive", renames)
    assert favs["games"]["megadrive"] == ["sonic-the-hedgehog"]
    assert credits == {"sonic-the-hedgehog/Boss Versus": {"author": "francesc"}}


def test_delete_is_marked_kept_and_restored():
    doc = store.empty("megadrive")
    store.merge(doc, "batocera", [{"path": "A.md", "header": None}, {"path": "B.md", "header": None}], NOW)
    c, _, _ = store.merge(doc, "batocera", [{"path": "A.md", "header": None}], LATER)
    b = doc["games"]["b"]["files"][0]
    assert c["deleted"] == 1 and b["status"] == "deleted" and b["lastSeen"] == NOW
    c, _, _ = store.merge(doc, "batocera", [{"path": "A.md", "header": None}, {"path": "B.md", "header": None}], LATER)
    assert c["restored"] == 1 and b["status"] == "present" and b["lastSeen"] == LATER


def test_other_nodes_untouched_by_a_scan():
    doc = store.empty("megadrive")
    store.merge(doc, "megadrive", [{"path": "A.md", "header": None}], NOW)
    store.merge(doc, "batocera", [], LATER)
    assert doc["games"]["a"]["files"][0]["status"] == "present"


def test_save_load_roundtrip():
    root = tempfile.mkdtemp()
    doc = store.empty("megadrive")
    store.merge(doc, "batocera", [{"path": "Sonic the Hedgehog (USA, Europe).md", "header": SONIC_H}], NOW)
    store.save(root, doc)
    assert store.load(root, "megadrive") == doc
    assert store.load(root, "saturn") == store.empty("saturn")


# -- batocera sync (scan + gamelist + favourites) ----------------------------

def batocera_megadrive():
    """A fake /userdata/roms/megadrive: fixture gamelist + synthesised ROMs + media."""
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(FIXTURES, "batocera", "megadrive", "gamelist.xml"), d)
    rom = md_rom(b"GM 00001009-00", b"SONIC THE HEDGEHOG")
    for name, data in [("Sonic the Hedgehog (USA, Europe).md", rom),
                       ("Sonic 1 Boss Mod [Boss Versus v0.3].md", rom),
                       ("Streets of Rage 2 (USA).zip", b"PK\x03\x04"),
                       ("CDRomance.url", b"[InternetShortcut]"), ("gamelist.xml.old", b"<x/>")]:
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    os.makedirs(os.path.join(d, "images"))
    open(os.path.join(d, "images", "Sonic the Hedgehog (USA, Europe)-image.png"), "wb").close()
    return d


def test_scan_skips_media_and_reads_headers():
    got = {g["path"]: g for g in scan.scan_dir(batocera_megadrive(), "megadrive")}
    assert sorted(got) == ["Sonic 1 Boss Mod [Boss Versus v0.3].md",
                           "Sonic the Hedgehog (USA, Europe).md", "Streets of Rage 2 (USA).zip"]
    assert got["Sonic the Hedgehog (USA, Europe).md"]["header"]["id"] == "GM 00001009-00"
    assert got["Streets of Rage 2 (USA).zip"]["header"] is None


def test_scan_disc_descriptors_consume_tracks():
    d = tempfile.mkdtemp()
    ip = ipbin(b"SEGA SEGAKATANA ", 0x40, b"HDR-0073", 0x80, b"SHENMUE", True, 0x30, b"J  ")
    with open(os.path.join(d, "Shenmue (Japan).gdi"), "w") as f:
        f.write('3\n1 0 4 2352 track01.bin 0\n2 756 0 2352 "track 02.raw" 0\n3 45000 4 2352 track03.bin 0\n')
    for fn, data in [("track01.bin", b""), ("track 02.raw", b""), ("track03.bin", ip)]:
        with open(os.path.join(d, fn), "wb") as f:
            f.write(data)
    got = scan.scan_dir(d, "dreamcast")
    assert [g["path"] for g in got] == ["Shenmue (Japan).gdi"]
    assert got[0]["header"]["id"] == "HDR-0073"


def test_remote_script_runs_standalone():
    """The SSH path: the packed program must run with nothing but python3 and argv."""
    d = batocera_megadrive()
    out = subprocess.run([sys.executable, "-c", scan.remote_script(), d, "megadrive"],
                         stdout=subprocess.PIPE, cwd=tempfile.gettempdir())
    got = scan.parse_output("banner noise\n" + out.stdout.decode())
    assert got == scan.scan_dir(d, "megadrive")


def test_failed_scan_raises_instead_of_merging():
    try:
        scan.parse_output("ssh: connect to host batocera port 22: Connection refused")
    except ValueError:
        return
    assert False, "a failed scan must not look like an empty one"


def test_gamelist_and_one_time_favourite_import():
    d = batocera_megadrive()
    with open(os.path.join(d, "gamelist.xml")) as f:
        gl = gamelist.parse(f.read())
    doc = store.empty("megadrive")
    store.merge(doc, "batocera", scan.scan_dir(d, "megadrive"), NOW)
    store.apply_scraped(doc, "batocera", gl)
    sonic = [f for f in doc["games"]["sonic-the-hedgehog"]["files"] if not f["variants"]][0]
    assert sonic["scraped"]["image"] == "images/Sonic the Hedgehog (USA, Europe)-image.png"

    favs = {"games": {}, "imported": {}}
    assert store.import_favourites(favs, doc, "batocera", gl, NOW) == 1   # "Gone From Disk" has no file
    assert favs["games"] == {"megadrive": ["sonic-the-hedgehog"]}
    favs["games"]["megadrive"] = []                                      # un-starred in Pluto
    assert store.import_favourites(favs, doc, "batocera", gl, LATER) is None
    assert favs["games"]["megadrive"] == []


def test_broken_gamelist_is_empty():
    assert gamelist.parse("<gameList><game>") == {}


# -- service: sync over a fake ssh + the merged view -------------------------

def fake_ssh(node, argv, stdin=None):
    """Run the would-be-remote program locally, exactly as ssh would hand it argv + stdin."""
    assert len(" ".join(argv)) < 9000, "remote command too long for dropbear"
    r = subprocess.run([sys.executable] + argv[1:], input=stdin.encode() if stdin else None,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, "motd banner\n" + r.stdout.decode()


CONFIG = {"nodeConsoles": {"batocera": ["*"], "megadrive": ["megadrive"], "dc": ["dreamcast"]},
          "systems": {"megadrive": {"name": "Mega Drive", "header": "megadrive"}, "snes": {"name": "Super Nintendo"}}}


def test_sync_all_then_view_merges_physical_into_one_row():
    roms, root = tempfile.mkdtemp(), tempfile.mkdtemp()
    os.rename(batocera_megadrive(), os.path.join(roms, "megadrive"))
    os.makedirs(os.path.join(roms, "snes"))                     # empty system: not listed
    os.makedirs(os.path.join(roms, "pygame"))                   # ignored system: never listed
    open(os.path.join(roms, "pygame", "game.pygame"), "w").write("x")
    lines = []
    assert service.sync(root, "*", dict(CONFIG, ignoreSystems=["pygame"]), fake_ssh, lambda s: {"sonic the hedgehog (usa, europe)": ["batocera"]},
                        lines.append, NOW, roms=roms)["merged"] == 1
    assert any(l.startswith("batocera/megadrive: 3 added") for l in lines), lines
    assert any("favourites imported" in l for l in lines)

    with open(os.path.join(root, "megadrive", "physical.json"), "w") as f:
        f.write('{"items": [{"title": "Sonic the Hedgehog", "id": "GM 00001009-00", "format": "Cartridge"},'
                ' {"title": "Ecco the Dolphin", "format": "Cartridge"}]}')
    view = service.system_view(root, "megadrive")
    by = {g["key"]: g for g in view["games"]}
    assert [g["title"] for g in view["games"]] == ["Ecco the Dolphin", "Sonic the Hedgehog", "Streets of Rage 2"]
    sonic = by["sonic-the-hedgehog"]
    assert len(sonic["files"]) == 2 and len(sonic["physical"]) == 1          # ROM + mod + shelf copy, one row
    assert sonic["favourite"] and sonic["saves"] == ["batocera"] and sonic["nodes"] == ["batocera"]
    assert by["ecco-the-dolphin"]["files"] == [] and by["ecco-the-dolphin"]["physical"]
    assert [s["system"] for s in service.systems(root)] == ["megadrive"]


def test_sync_all_marks_an_emptied_system_deleted():
    roms, root = tempfile.mkdtemp(), tempfile.mkdtemp()
    os.rename(batocera_megadrive(), os.path.join(roms, "megadrive"))
    service.sync(root, "*", CONFIG, fake_ssh, None, lambda l: None, NOW, roms=roms)
    shutil.rmtree(os.path.join(roms, "megadrive"))
    service.sync(root, "*", CONFIG, fake_ssh, None, lambda l: None, LATER, roms=roms)
    files = [f for g in store.load(root, "megadrive")["games"].values() for f in g["files"]]
    assert files and all(f["status"] == "deleted" for f in files)


def test_unreachable_batocera_warns_and_the_rest_still_syncs():
    lib, root, lines = tempfile.mkdtemp(), tempfile.mkdtemp(), []
    os.makedirs(os.path.join(lib, "megadrive", "roms"))
    open(os.path.join(lib, "megadrive", "roms", "Ecco the Dolphin (USA).md"), "wb").close()
    cfg = dict(CONFIG, nodeConsoles={"batocera": ["*"], "lab": ["*"], "megadrive": ["megadrive"]})
    got = service.sync(root, "megadrive", cfg, lambda n, a, stdin=None: (255, "ssh: Connection refused"),
                       None, lines.append, NOW, lab_roms=lib)
    assert got == {"merged": 1, "skipped": 1}, lines
    assert any(l.startswith("WARN batocera: scan failed, skipped") for l in lines)
    assert "megadrive: not built yet, skipped" in lines
    files = [f for g in store.load(root, "megadrive")["games"].values() for f in g["files"]]
    assert [f["node"] for f in files] == ["lab"]


def test_one_bad_system_does_not_stop_the_others():
    root, lines = tempfile.mkdtemp(), []
    found = {"megadrive": {"files": [{"path": "A.md", "header": None}], "gamelist": ""},
             "snes": {"files": [{"path": "B.sfc"}], "gamelist": "<gameList><game><path>./B.sfc"}}
    real_merge = store.merge
    def flaky(doc, node, scan_, now, scope=None, strip=None):
        if doc["system"] == "megadrive":
            raise IOError("disk hiccup")
        return real_merge(doc, node, scan_, now, scope, strip)
    store.merge = flaky
    try:
        got = service.sync(root, "*", dict(CONFIG, nodeConsoles={"batocera": ["*"]}),
                           lambda n, a, stdin=None: (0, "--CPC-GAMELIST--\n%s\n--CPC-GAMELIST--" % json.dumps(found)),
                           None, lines.append, NOW)
    finally:
        store.merge = real_merge
    assert got == {"merged": 1, "skipped": 1}, lines
    assert any("WARN batocera/megadrive: merge failed" in l for l in lines)
    assert store.load(root, "snes")["games"]


# -- covers ------------------------------------------------------------------


def test_cover_matches_a_differently_spaced_art_name():
    """libretro writes OutRun, Space Harrier 3D, NewZealand Story: same game, own spelling."""
    art = ["OutRun (USA, Europe)", "Space Harrier 3D (World)", "NewZealand Story, The (Europe)",
           "Wimbledon (Europe)"]
    def game(title):
        return {"key": names.key(title), "title": title, "files": [], "physical": []}
    assert covers.best_match(game("Out Run"), art) == "OutRun (USA, Europe)"
    assert covers.best_match(game("Space Harrier 3-D"), art) == "Space Harrier 3D (World)"
    assert covers.best_match(game("New Zealand Story, The"), art) == "NewZealand Story, The (Europe)"
    assert covers.best_match(game("Wimbledon II"), art) is None      # a sequel is another game

class _NotFound(Exception):
    code = 404


class _Resp(object):
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.data


def test_cover_candidates_and_cache():
    game = {"key": "sonic-the-hedgehog", "title": "Sonic the Hedgehog", "files": [
        {"path": "hacks/Sonic [Boss Versus].md", "status": "present", "variants": [{"kind": "mod", "name": "Boss Versus"}]},
        {"path": "Sonic the Hedgehog (USA, Europe) [!].md", "status": "present", "variants": [{"kind": "mod", "name": "!"}]},
        {"path": "Sonic the Hedgehog (Japan).md", "status": "present", "variants": []},
        {"path": "Gone: Deleted (Japan).md", "status": "deleted", "variants": []}]}
    c = covers.candidates(game)
    assert c[0] == "Sonic the Hedgehog (Japan)"                      # originals first, deleted skipped
    assert "Sonic the Hedgehog (USA, Europe)" in c and c[-1] == "Sonic the Hedgehog"

    root, asked = tempfile.mkdtemp(), []
    def opener(req, timeout):
        asked.append(req.full_url)
        if "git/trees" in req.full_url:
            raise IOError("rate limited")        # no index: exact candidates only
        if "USA" in req.full_url:
            return _Resp(b"\x89PNG\r\n\x1a\nart")
        raise _NotFound()
    path = covers.fetch(root, "megadrive", game, "Sega_-_Mega_Drive_-_Genesis", opener)
    assert path and open(path, "rb").read().endswith(b"art") and "Sega_-_Mega_Drive_-_Genesis" in asked[0]
    n = len(asked)
    assert covers.fetch(root, "megadrive", game, "x", opener) == path and len(asked) == n   # cached, no refetch

    assert covers.fetch(root, "megadrive", dict(game, key="norepo"), None, opener) is None
    assert covers.cached(root, "megadrive", "norepo") is None          # no repo: not a miss
    with open(os.path.join(root, "megadrive", "covers", "_index.json"), "w") as f:
        json.dump([], f)                                             # art list loaded: a clean miss
    lost = dict(game, key="lost", files=[], title="Nope")
    assert covers.fetch(root, "megadrive", lost, "x", opener) is None and covers.cached(root, "megadrive", "lost") == "miss"
    covers.clear_misses(root, "megadrive")
    assert covers.cached(root, "megadrive", "lost") is None


def test_uploaded_cover_wins_and_is_validated():
    root = tempfile.mkdtemp()
    game = {"key": "akira", "title": "AkiraGBC", "files": []}
    def never(req, timeout):
        raise AssertionError("uploaded art must not hit the network")
    try:
        covers.save_custom(root, "gbc", "akira", b"<html>nope")
        assert False, "non-image accepted"
    except ValueError:
        pass
    covers.save_custom(root, "gbc", "akira", b"\x89PNG\r\n\x1a\nfirst")
    jpg = covers.save_custom(root, "gbc", "akira", b"\xff\xd8\xff\xe0second")      # replace, new type
    assert os.listdir(os.path.join(root, "gbc", "art")) == ["akira.jpg"]
    assert covers.fetch(root, "gbc", game, "Nintendo_-_Game_Boy_Color", never) == jpg
    covers.clear_misses(root, "gbc")
    assert covers.custom(root, "gbc", "akira") == jpg


def test_network_trouble_is_not_cached_as_a_miss():
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "sms", "covers"))
    with open(os.path.join(root, "sms", "covers", "_index.json"), "w") as f:
        json.dump(["Zillion (USA, Europe) (Rev 1)"], f)
    game = {"key": "zillion", "title": "Zillion", "files": [{"path": "Zillion (USA, Europe) (Rev 1).zip", "status": "present", "variants": []}]}
    def offline(req, timeout):
        raise IOError("timed out")
    assert covers.fetch(root, "sms", game, "Sega_-_Master_System_-_Mark_III", offline) is None
    assert covers.cached(root, "sms", "zillion") is None           # retried next time, not a miss


def test_batocera_scraped_image_is_a_cover_source():
    root = tempfile.mkdtemp()
    doc = store.empty("mame")
    store.merge(doc, "batocera", [{"path": "sf2.zip", "header": None}], NOW)
    store.apply_scraped(doc, "batocera", {"sf2.zip": {"name": "Street Fighter II", "image": "images/sf2-image.png", "thumbnail": "images/sf2-thumb.jpg"}})
    store.save(root, doc)
    asked = []
    def read(node, path):
        asked.append((node, path))
        return b"\xff\xd8\xff\xe0jpegdata"
    path = service.cover(root, "mame", "sf2", {"systems": {}}, read)
    assert path and path.endswith("sf2.jpg") and asked == [("batocera", "/userdata/roms/mame/images/sf2-thumb.jpg")]   # box art, never the screenshot
    assert service.cover(root, "mame", "sf2", {"systems": {}}, read) == path and len(asked) == 1     # cached
    assert covers.linked(root, "mame", "sf2")


def test_cover_linked_is_local_only():
    root = tempfile.mkdtemp()
    assert covers.linked(root, "gbc", "akira") is False
    covers.save_custom(root, "gbc", "akira", b"\x89PNG\r\n\x1a\nx")
    assert covers.linked(root, "gbc", "akira") is True


def test_cover_index_matches_on_title_and_tags():
    game = {"key": "sonic-the-hedgehog", "title": "Sonic The Hedgehog", "files": [
        {"path": "Sonic The Hedgehog (USA, Europe).zip", "status": "present", "variants": []}]}
    art = ["Sonic The Hedgehog (Japan)", "Sonic The Hedgehog (USA, Europe, Brazil) (En)",
           "Sonic The Hedgehog 2 (Europe, Brazil) (En)", "Sonic Chaos (Europe, Brazil) (En)"]
    assert covers.best_match(game, art) == "Sonic The Hedgehog (USA, Europe, Brazil) (En)"
    assert covers.best_match(dict(game, title="Sonic Blast"), art) is None
    root, served = tempfile.mkdtemp(), {"Real (Europe).png": b"\x89PNG\r\n\x1a\nreal", "Dup (Europe).png": b"Real (Europe).png"}
    def opener(req, timeout):
        name = req.full_url.rsplit("/", 1)[-1].replace("%20", " ").replace("%28", "(").replace("%29", ")")
        if "git/trees" in req.full_url:
            raise IOError("no index")
        if name in served:
            return _Resp(served[name])
        raise _NotFound()
    dup = {"key": "dup", "title": "Dup", "files": [{"path": "Dup (Europe).bin", "status": "present", "variants": []}]}
    path = covers.fetch(root, "psx", dup, "Sony_-_PlayStation", opener)
    assert path and open(path, "rb").read().endswith(b"real")                  # symlink followed
    lol = {"title": "L.O.L. - Lack of Love", "files": []}
    assert covers.best_match(lol, ["L.O.L. - Lack of Love (Japan)"]) == "L.O.L. - Lack of Love (Japan)"


# -- local library (lab): roms/ only, saves skipped, zips opened --------------

def test_lab_scans_roms_dirs_only_with_zip_headers_and_no_saves():
    import zipfile
    lib, root = tempfile.mkdtemp(), tempfile.mkdtemp()
    rom = md_rom(b"GM 00001009-00", b"SONIC THE HEDGEHOG")
    os.makedirs(os.path.join(lib, "megadrive", "roms"))
    os.makedirs(os.path.join(lib, "megadrive", "bios"))
    os.makedirs(os.path.join(lib, "notasystem"))
    with zipfile.ZipFile(os.path.join(lib, "megadrive", "roms", "sonic.zip"), "w") as z:
        z.writestr("__MACOSX/._x", b"junk")
        z.writestr("Sonic the Hedgehog (USA, Europe).md", rom)
    for rel, data in [("megadrive/roms/Sonic the Hedgehog (USA, Europe).srm", b"save"),
                      ("megadrive/roms/Sonic the Hedgehog (USA, Europe).state1", b"state"),
                      ("megadrive/bios/bios.bin", b"bios"), ("notasystem/x.bin", b"x")]:
        with open(os.path.join(lib, rel), "wb") as f:
            f.write(data)
    cfg = dict(CONFIG, nodeConsoles={"lab": ["*"]}, savePatterns={"megadrive": [".srm"]},
               saveFormats={"stateContains": [".state"]})
    lines = []
    service.sync(root, "*", cfg, None, None, lines.append, NOW, lab_roms=lib)
    files = [f for g in store.load(root, "megadrive")["games"].values() for f in g["files"]]
    assert [f["path"] for f in files] == ["sonic.zip"], lines
    assert files[0]["inner"] == "Sonic the Hedgehog (USA, Europe).md" and files[0]["id"] == "GM 00001009-00"
    assert sorted(os.listdir(root)) == ["favourites.json", "megadrive"]


# -- metadata ----------------------------------------------------------------

DAT_GENRE = """clrmamepro (
\tname "Sega - Mega Drive - Genesis"
)

game (
\tcomment "Sonic The Hedgehog (USA, Europe)"
\tgenre "Platform"
\trom ( crc F9394E97 )
)

game (
\tcomment "Sonic The Hedgehog (Japan, Korea)"
\tgenre "Platform (JP)"
\trom ( crc AFE05EEE )
)

game (
   developer "Toys for Bob"
\tserial "T-36813D-05"
\trom ( name "102 Dalmatians (UK) (Track 1).bin" size 1 crc CDCC8DB8 serial "T-36813D-05" )
)
"""


def test_metadata_parse_and_match():
    genre = metadata.parse_dat(DAT_GENRE, "genre")
    assert [e["value"] for e in genre] == ["Platform", "Platform (JP)"]
    dev = metadata.parse_dat(DAT_GENRE, "developer")
    assert dev == [{"name": "102 Dalmatians (UK)", "value": "Toys for Bob", "serial": "T-36813D-05"}]

    sonic = {"title": "Sonic The Hedgehog", "ids": [], "files": [
        {"path": "Sonic The Hedgehog (USA, Europe) [Knuckles].bin", "status": "present", "variants": [{"kind": "mod", "name": "Knuckles"}]}]}
    assert metadata.lookup(sonic, metadata.index(genre)) == "Platform"            # key + shared tags
    by_id = {"title": "Anything", "ids": ["T36813D05"], "files": []}                 # dashes ignored
    assert metadata.lookup(by_id, metadata.index(dev)) == "Toys for Bob"          # serial wins


def test_metadata_annotate_caches_and_tolerates_missing_files():
    import urllib.error
    root, asked = tempfile.mkdtemp(), []
    def opener(req, timeout):
        asked.append(req.full_url)
        if "/genre/" in req.full_url:
            return _Resp(DAT_GENRE.encode())
        raise urllib.error.HTTPError(req.full_url, 404, "nf", None, None)
    doc = store.empty("megadrive")
    store.merge(doc, "lab", [{"path": "Sonic The Hedgehog (USA, Europe).md", "header": None}], NOW)
    assert metadata.annotate(root, "megadrive", doc, "Sega_-_Mega_Drive_-_Genesis", opener) == 1
    assert doc["games"]["sonic-the-hedgehog"]["meta"] == {"genre": "Platform"}
    assert "Sega%20-%20Mega%20Drive%20-%20Genesis" in asked[0]
    n = len(asked)
    metadata.annotate(root, "megadrive", doc, "Sega_-_Mega_Drive_-_Genesis", opener)
    assert len(asked) == n                                                       # cached, incl. the 404s


def test_sd_cards_on_one_node_never_delete_each_other():
    doc = store.empty("saturn")
    store.merge(doc, "saturn", [{"path": "SAROO/ISO/A/A.cue", "header": None}], NOW, scope="SAROO/")
    store.merge(doc, "saturn", [{"path": "SAROO2/ISO/B/B.cue", "header": None}], NOW, scope="SAROO2/")
    c, _, _ = store.merge(doc, "saturn", [], LATER, scope="SAROO2/")          # SAROO2 emptied
    status = {f["path"]: f["status"] for g in doc["games"].values() for f in g["files"]}
    assert c["deleted"] == 1 and status == {"SAROO/ISO/A/A.cue": "present", "SAROO2/ISO/B/B.cue": "deleted"}


def test_sd_sync_scans_each_card_through_the_hub():
    root, lines, calls = tempfile.mkdtemp(), [], []
    card = tempfile.mkdtemp()
    os.makedirs(os.path.join(card, "ISO", "Wing Arms (Europe)"))
    open(os.path.join(card, "ISO", "Wing Arms (Europe)", "Wing Arms (Europe).cue"), "w").write('FILE "t.bin" BINARY\n')
    def run_ssh(node, argv, stdin=None):
        calls.append((node, argv[2]))
        if argv[2] == "SAROO2":
            return 2, "no card labelled SAROO2 in the hub"
        files = scan.scan_dir(os.path.join(card, argv[3]), None, json.loads(argv[5]))   # what the Pi would return
        return 0, scan.BEGIN + "\n" + json.dumps(files) + "\n" + scan.END
    cfg = dict(CONFIG, nodeConsoles={"saturn": ["saturn"]})
    got = service.sync(root, "saturn", cfg, run_ssh, None, lines.append, NOW,
                       sd_nodes={"saturn": {"labels": ["SAROO", "SAROO2"], "roms_dir": "ISO", "hub": "pi"}})
    assert calls == [("pi", "SAROO"), ("pi", "SAROO2")] and got["merged"] == 1, lines
    assert any("card SAROO2" in l for l in lines)
    files = [f["path"] for g in store.load(root, "saturn")["games"].values() for f in g["files"]]
    assert files == ["SAROO/Wing Arms (Europe)/Wing Arms (Europe).cue"]
    assert [f["card"] for g in store.load(root, "saturn")["games"].values() for f in g["files"]] == ["SAROO"]


def test_label_is_global_names_the_game_and_drives_its_art():
    root = tempfile.mkdtemp()
    doc = store.empty("saturn")
    store.merge(doc, "saturn", [{"path": "SAROO/kof95.bin", "header": None}], NOW)
    os.makedirs(os.path.join(root, "saturn", "covers"))
    store.save(root, doc)
    open(os.path.join(root, "saturn", "covers", "kof95.miss"), "w").close()
    service.set_label(root, "saturn", "kof95", "King of Fighters '95, The (Japan)")
    g = service.system_view(root, "saturn")["games"][0]
    assert (g["key"], g["title"], g["fileTitle"]) == ("kof95", "King of Fighters '95, The (Japan)", "kof95")
    assert g["cover"] is None                                   # the old miss is forgotten
    assert covers.candidates(g)[0] == "King of Fighters '95, The (Japan)"
    art = ["King of Fighters '95, The (Japan) (1M)", "King of Fighters '95, The (Europe)"]
    assert covers.best_match(g, art) in art
    assert store.load_labels(root) == {"saturn": {"kof95": "King of Fighters '95, The (Japan)"}}
    # follows a rekey; empty clears
    labels = store.load_labels(root)
    store.rekey_labels(labels, "saturn", {"kof95": "kof-95"})
    assert labels == {"saturn": {"kof-95": "King of Fighters '95, The (Japan)"}}
    service.set_label(root, "saturn", "kof95", "")
    assert store.load_labels(root) == {} and service.system_view(root, "saturn")["games"][0]["title"] == "kof95"


def test_one_card_feeds_several_systems_by_extension():
    root = tempfile.mkdtemp()
    calls = []
    def run_ssh(node, argv, stdin=None):
        calls.append(json.loads(argv[4]) if argv[4] else None)
        files = [{"path": "01 USA Games (A-M)/Aladdin (USA).bin", "size": 1, "inner": None, "header": None},
                 {"path": "Master Games/Alex Kidd in Miracle World (USA, Europe).sms", "size": 1, "inner": None, "header": None}]
        return 0, "%s\n%s\n%s\n" % (scan.BEGIN, json.dumps(files), scan.END)
    cfg = dict(CONFIG, nodeConsoles={"megadrive": ["megadrive", "mastersystem"]},
               systems={"megadrive": {"header": "megadrive"}, "mastersystem": {"header": "sms", "extensions": [".sms"]}})
    got = service.sync(root, "*", cfg, run_ssh, None, lambda l: None, NOW,
                       sd_nodes={"megadrive": {"labels": ["EDMD"], "roms_dir": ".", "hub": "pi"}})
    assert calls == [{"*": "megadrive", ".sms": "sms"}] and got["merged"] == 2, (calls, got)
    md = [f["path"] for g in store.load(root, "megadrive")["games"].values() for f in g["files"]]
    ms = [f["path"] for g in store.load(root, "mastersystem")["games"].values() for f in g["files"]]
    assert md == ["EDMD/01 USA Games (A-M)/Aladdin (USA).bin"] and ms == ["EDMD/Master Games/Alex Kidd in Miracle World (USA, Europe).sms"]
    # one system's sync leaves the other system's list alone
    store.merge(store.load(root, "mastersystem"), "megadrive", [], NOW)
    service.sync(root, "megadrive", cfg, run_ssh, None, lambda l: None, LATER,
                 sd_nodes={"megadrive": {"labels": ["EDMD"], "roms_dir": ".", "hub": "pi"}})
    assert [f["status"] for g in store.load(root, "mastersystem")["games"].values() for f in g["files"]] == ["present"]


def test_physical_copy_joins_its_rom_and_lists_when_shelf_only():
    root = tempfile.mkdtemp()
    doc = store.empty("saturn")
    store.merge(doc, "batocera", [{"path": "Winter Heat (Japan).chd", "header": {"id": "GS-9177", "title": "WINTER HEAT", "regions": ["Japan"]}}], NOW)
    os.makedirs(os.path.join(root, "saturn"))
    store.save(root, doc)
    with open(os.path.join(root, "saturn", "physical.json"), "w") as f:
        json.dump({"items": [
            {"title": "Winter Heat (Japan)", "id": "GS-9177", "format": "CD", "status": "Complete", "notes": ""},
            {"title": "SimCity 2000 (Japan) (Rev A)", "id": "GS-9027", "format": "CD", "status": "Disc only", "notes": "two-disc case"},
        ]}, f)
    games = {g["key"]: g for g in service.system_view(root, "saturn")["games"]}
    assert set(games) == {"winter-heat", "simcity-2000"}
    assert games["winter-heat"]["nodes"] == ["batocera"] and games["winter-heat"]["physical"][0]["status"] == "Complete"
    sc = games["simcity-2000"]
    assert sc["title"] == "SimCity 2000" and sc["regions"] == ["Japan"] and sc["ids"] == ["GS-9027"] and not sc["files"]
    assert covers.candidates(sc)[0] == "SimCity 2000 (Japan) (Rev A)"
    assert service.physical_only(root) == {"games": [{"system": "saturn", "key": "simcity-2000", "title": "SimCity 2000"}]}


def test_kind_marks_tools_across_digital_and_physical():
    root = tempfile.mkdtemp()
    doc = store.empty("dreamcast")
    store.merge(doc, "batocera", [{"path": "Dreamkey 3.1 (Spain)/Dreamkey 3.1 (Spain).gdi", "header": None}], NOW)
    os.makedirs(os.path.join(root, "dreamcast"))
    store.save(root, doc)
    with open(os.path.join(root, "dreamcast", "physical.json"), "w") as f:
        json.dump({"items": [{"title": "Dreamkey 3.1 (Spain)", "format": "GD-ROM"}, {"title": "Maken X (Europe)"}]}, f)
    with open(os.path.join(root, "kinds.json"), "w") as f:
        json.dump({"dreamcast": {"dreamkey-3-1": "tool"}}, f)
    kinds = {g["key"]: (g["kind"], bool(g["nodes"]), len(g["physical"])) for g in service.system_view(root, "dreamcast")["games"]}
    assert kinds == {"dreamkey-3-1": ("tool", True, 1), "maken-x": ("game", False, 1)}


def test_admin_node_prints_its_command_and_a_posted_list_merges_like_a_scan():
    root, lines = tempfile.mkdtemp(), []
    cfg = dict(CONFIG, nodeConsoles={"ps2": ["ps2"]})
    service.sync(root, "ps2", cfg, fake_ssh, None, lines.append, NOW, admin_nodes={"ps2": "sudo ps2hdd.py sync"})
    assert "ps2: needs admin, run in Terminal: sudo ps2hdd.py sync" in lines, lines

    service.merge_posted(root, "ps2", "ps2", [{"path": "Futurama (USA).iso", "size": 1}, {"path": "Okami (Europe).iso", "size": 2}],
                         cfg, None, lines.append, NOW)
    service.merge_posted(root, "ps2", "ps2", [{"path": "Futurama (USA).iso", "size": 1}], cfg, None, lines.append, LATER)
    status = {f["path"]: f["status"] for g in store.load(root, "ps2")["games"].values() for f in g["files"]}
    assert status == {"Futurama (USA).iso": "present", "Okami (Europe).iso": "deleted"}, status
    game = next(k for k, g in store.load(root, "ps2")["games"].items() if g["title"] == "Okami")
    try:
        service.forget_file(root, "ps2", "futurama", "ps2", "Futurama (USA).iso")
        assert False, "a present copy can't be forgotten"
    except ValueError:
        pass
    service.forget_file(root, "ps2", game, "ps2", "Okami (Europe).iso")
    assert game not in store.load(root, "ps2")["games"]
    try:
        service.merge_posted(root, "megadrive", "ps2", [], cfg, None, lines.append, NOW)
        assert False, "a node may only post systems it hosts"
    except ValueError:
        pass


def test_systems_count_tools_translations_and_mods():
    root = tempfile.mkdtemp()
    doc = store.empty("megadrive")
    store.merge(doc, "batocera", [{"path": "Sonic the Hedgehog (USA, Europe).md", "header": None},
                                  {"path": "Sonic the Hedgehog (Europe) [T-Cat v0.6].md", "header": None},
                                  {"path": "Sonic the Hedgehog (Europe) [T-Cat v0.7].md", "header": None},
                                  {"path": "Sonic the Hedgehog (Europe) [Boss Versus v0.3].md", "header": None},
                                  {"path": "Everdrive Menu.md", "header": None}], NOW)
    os.makedirs(os.path.join(root, "megadrive")); store.save(root, doc)
    with open(os.path.join(root, "kinds.json"), "w") as f:
        json.dump({"megadrive": {"everdrive-menu": "tool"}}, f)
    s = service.systems(root)[0]
    assert (s["games"], s["tools"], s["translations"], s["mods"]) == (2, 1, 1, 1), s


def test_send_plan_skips_what_the_target_has_and_prefers_lab_sources():
    root = tempfile.mkdtemp()
    doc = store.empty("ps2")
    store.merge(doc, "batocera", [{"path": "Okami (Europe) (En,Fr,De).chd", "header": None},
                                  {"path": "Futurama (USA).iso", "header": None},
                                  {"path": "Kunoichi (Japan).iso", "header": None}], NOW)
    store.merge(doc, "lab", [{"path": "Okami (Europe) (En,Fr,De).7z", "header": None},
                             {"path": "Kunoichi (Japan) [T-En v1.0].7z", "header": None}], NOW)
    store.merge(doc, "ps2", [{"path": "Futurama (USA).iso", "header": None}], NOW)
    os.makedirs(os.path.join(root, "ps2")); store.save(root, doc)

    p = send.plan(root, "ps2", "ps2", ["lab", "batocera"], all_missing=True)
    got = sorted((c["name"], c["source"]["node"]) for c in p["copies"])
    assert got == [("Kunoichi (Japan)", "batocera"), ("Kunoichi (Japan) [T-En v1.0]", "lab"),
                   ("Okami (Europe)", "lab")], got
    assert [s["game"] for s in p["skipped"]] == ["Futurama"]
    picked = send.plan(root, "ps2", "ps2", ["lab", "batocera"], files=[{"node": "batocera", "path": "Okami (Europe) (En,Fr,De).chd"}])
    assert [(c["source"]["node"], c["name"]) for c in picked["copies"]] == [("batocera", "Okami (Europe)")]
    assert send.strategy_for({"PS2_HDD_BYTES": "1"}) == "hdd" and send.strategy_for({}) is None


def test_sd_strategy_copies_single_file_roms_and_skips_what_the_card_has():
    p = {"copies": [{"game": "a", "name": "Sonic (USA)", "source": {"node": "lab", "path": "Sonic (USA).zip", "inner": "Sonic (USA).md"}},
                    {"game": "b", "name": "Ecco (Europe)", "source": {"node": "batocera", "path": "Ecco (Europe).md"}},
                    {"game": "c", "name": "Snatcher (USA)", "source": {"node": "lab", "path": "Snatcher (USA).cue"}}],
         "skipped": []}
    put, events = [], []
    card = {"mount": lambda: events.append("mount"), "exists": lambda n: n == "Ecco (Europe).md",
            "put": lambda src, name: put.append((src, name)), "finish": lambda: events.append("finish") or ["rescanned"]}
    ctx = {"target": "megadrive", "card": card, "locate": lambda s: "/roms/" + s["path"], "unpack": True, "system": "megadrive",
           "rom_ext": lambda s: os.path.splitext(s.get("inner") or s["path"])[1]}
    got = send.STRATEGIES["sd"](p, ctx)
    assert put == [("/roms/Sonic (USA).zip", "Sonic (USA).md")], put
    assert got["status"] == "done" and got["count"] == 1 and events == ["mount", "finish"] and "rescanned" in got["lines"]
    assert sorted(s["game"] for s in p["skipped"]) == ["Ecco (Europe)", "Snatcher (USA)"]
    assert send.strategy_for({"SD_LABEL": "EDMD"}) is None and send.strategy_for({"SD_LABEL": "EDMD", "SD_ROMS_DIR": "Mega Drive"}) == "sd"
    nothing = send.STRATEGIES["sd"]({"copies": [], "skipped": []}, ctx)
    assert nothing["status"] == "done" and nothing["count"] == 0 and events == ["mount", "finish"]      # no mount for nothing


def test_send_copies_a_gdi_or_cue_disc_as_its_folder():
    gdi = '3\n1 0 4 2352 track01.bin 0\n2 600 0 2352 track02.raw 0\n3 45000 4 2352 "track 03.bin" 0\n'
    assert send.disc_tracks(gdi, ".gdi") == ["track01.bin", "track02.raw", "track 03.bin"]
    assert send.disc_tracks('FILE "A (Track 1).bin" BINARY\n  TRACK 01 MODE1/2352\nFILE "A (Track 2).bin" BINARY\n', ".cue") == ["A (Track 1).bin", "A (Track 2).bin"]
    p = {"copies": [{"game": "a", "name": "Tokyo Bus Guide (Japan) [Vanilla Build]",
                     "source": {"node": "lab", "path": "Tokyo Bus Guide (Japan) [Vanilla Build]/Tokyo Bus Guide (Japan) [Vanilla Build].gdi"}},
                    {"game": "b", "name": "Shenmue (Japan)", "source": {"node": "lab", "path": "Shenmue (Japan)/Shenmue (Japan).gdi"}},
                    {"game": "c", "name": "Game (USA)", "source": {"node": "lab", "path": "Game (USA).m3u"}}],
         "skipped": []}
    put = []
    card = {"mount": lambda: None, "exists": lambda n: n == "Shenmue (Japan)",
            "put": lambda src, name: put.append((src, name)), "finish": lambda: ["rescanned"]}
    def members(src, ext):
        d = src.rsplit("/", 1)[0]
        return [(src, src.rsplit("/", 1)[1], True)] + [(d + "/" + t, t, False) for t in ["track01.bin", "track02.raw", "track03.bin"]]
    ctx = {"target": "batocera", "card": card, "locate": lambda s: "/roms/" + s["path"], "system": "dreamcast",
           "rom_ext": lambda s: os.path.splitext(s["path"])[1], "members": members}
    got = send.STRATEGIES["batocera"](p, ctx)
    folder = "Tokyo Bus Guide (Japan) [Vanilla Build]"
    assert [n for _, n in put] == [folder + "/" + folder + ".gdi", folder + "/track01.bin", folder + "/track02.raw", folder + "/track03.bin"], put
    assert got["count"] == 1
    assert sorted((s["game"], s["why"]) for s in p["skipped"]) == [("Game (USA)", ".m3u disc images can't be sent yet"),
                                                                   ("Shenmue (Japan)", "already there as Shenmue (Japan)/")]


def test_tools_are_not_missing_covers():
    root = tempfile.mkdtemp()
    doc = store.empty("gamecube")
    store.merge(doc, "batocera", [{"path": "GCTestSuite.iso", "header": None}, {"path": "Ikaruga (Japan).iso", "header": None}], NOW)
    os.makedirs(os.path.join(root, "gamecube")); store.save(root, doc)
    with open(os.path.join(root, "kinds.json"), "w") as f:
        json.dump({"gamecube": {"gctestsuite": "tool"}}, f)
    assert [g["title"] for g in service.missing_covers(root)["games"]] == ["Ikaruga"]


def test_search_finds_games_across_systems_by_folded_title():
    root = tempfile.mkdtemp()
    for s, path in (("megadrive", "Sonic the Hedgehog (USA, Europe).md"), ("gamegear", "Sonic Chaos (Europe).gg"), ("snes", "Pokémon Stadium.sfc")):
        doc = store.empty(s)
        store.merge(doc, "batocera", [{"path": path, "header": None}], NOW)
        os.makedirs(os.path.join(root, s)); store.save(root, doc)
    got = sorted((g["system"], g["title"]) for g in service.search(root, "sonic")["games"])
    assert got == [("gamegear", "Sonic Chaos"), ("megadrive", "Sonic the Hedgehog")], got
    assert [g["title"] for g in service.search(root, "pokemon")["games"]] == ["Pokémon Stadium"]
    assert service.search(root, "  ")["games"] == []


def test_systems_carry_favourite_and_owned_console():
    root = tempfile.mkdtemp()
    for s in ("saturn", "mame"):
        doc = store.empty(s)
        store.merge(doc, "batocera", [{"path": "x.zip", "header": None}], NOW)
        os.makedirs(os.path.join(root, s)); store.save(root, doc)
    store.save_favourites(root, {"games": {}, "imported": {}})
    with open(os.path.join(root, "hardware.json"), "w") as f:
        json.dump({"consoles": {"saturn": {"status": "", "notes": ""}}}, f)
    service.set_system_favourite(root, "mame", True)
    got = {s["system"]: (s["favourite"], s["owned"]) for s in service.systems(root)}
    assert got == {"saturn": (False, True), "mame": (True, False)}
    service.set_system_favourite(root, "mame", False)
    assert store.load_favourites(root)["systems"] == []


def test_cover_falls_back_to_another_systems_art():
    root = tempfile.mkdtemp()
    game = {"key": "virtua-tennis", "title": "Virtua Tennis", "files": [], "physical": [{"title": "Virtua Tennis"}]}
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    class R:
        def __init__(self, data): self.data = data
        def read(self): return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def opener(req, timeout=None):
        url = req.full_url
        if "git/trees" in url:
            names_ = ["Virtua Tennis (Europe)"] if "Dreamcast" in url else ["Other Game (Japan)"]
            return R(json.dumps({"tree": [{"path": "Named_Boxarts/%s.png" % n} for n in names_]}).encode())
        if "Dreamcast" in url and "Virtua%20Tennis" in url:
            return R(png)
        from urllib.error import HTTPError
        raise HTTPError(url, 404, "nf", None, None)
    path = covers.fetch(root, "naomi", game, ["Sega_-_Naomi", "Sega_-_Dreamcast"], opener)
    assert path and path.endswith("naomi/covers/virtua-tennis.png")
    assert sorted(os.listdir(os.path.join(root, "naomi", "covers"))) == ["_index-Sega_-_Dreamcast.json", "_index.json", "virtua-tennis.png"]
    # nothing anywhere -> one clean miss
    assert covers.fetch(root, "naomi", dict(game, key="nope", title="Nope", physical=[]), ["Sega_-_Naomi", "Sega_-_Dreamcast"], opener) is None
    assert covers.cached(root, "naomi", "nope") == "miss"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print("%d tests passed" % len(tests))
