# Dreamcast — Translation Guide

## Disc format

GDI (preferred) — 5 tracks, dual session. Data in track 3 (low-density, ~300MB) and track 5 (high-density, ~825MB). Filesystem directory lives in track 3; files may physically reside in either track. Always check the LBA against track boundaries before reading.

Track boundaries from disc.gdi:
- Track 3 (data): starts at disc LBA 45000
- Track 5 (data): starts at disc LBA 181308

Read relative offset = absolute LBA - track_start_LBA.

## Extraction

ISO9660 filesystem, 2352-byte raw sectors, Mode 1 data at byte offset 16 within each sector. No special library needed — stdlib `struct` + direct file read.

`STORY.PAC` stores story/dialogue as a Sega SCP archive (magic `SCP\0`). Text is Shift-JIS embedded at known offsets — searchable directly without parsing the SCP directory format.

## Text format

**Per-game variation** — Dreamcast games use different text storage methods. No universal approach.

Common patterns:
- ISO directory-based: `DPETC/MESSAGE.INI` (UI), `STORY.PAC` (dialogue, raw Shift-JIS)
- Track 5 raw: Speaker-tagged dialogue (`\x02\xff[id]\x00` + Shift-JIS text)
- **Game-specific**: Check `pluto/translation/games/` for per-title extraction method

## Recon: finding the text in a new game

DC has **no standard** text format or filename, so don't trust a fixed name list.
Find the text by **content, not name**:

1. Extract the disc, then **scan every file for dense Shift-JIS double-byte runs**
   (same lead/trail test as `dc_story_extract`: lead `0x81-0x9F`/`0xE0-0xEF` + trail
   `0x40-0x7E`/`0x80-0xFC`). The files with the most runs hold the dialogue.
2. Names are a *hint*, not a rule: you may see `*.PAC`/`*.AFS`/`*.MRG` containers,
   `MESSAGE`/`MSG`/`SUBTITLE`/`SCRIPT`/`SCN` stems, or `TEXT/`/`SCN/`/`<LANG>/` dirs,
   but many titles use bespoke names with no convention at all.
3. A plain-INI UI file (Boku Doraemon's `DPETC/MESSAGE.INI`) is the easiest win when
   present; cutscene/subtitle blobs are usually binary inside a container.

The `no STORY.PAC in this disc` error is exactly this signal: that game keeps its
text elsewhere. Run the content scan to find where, then add a `games/<title>.md`.

## Font situation

`DPFONT/` contains four sizes of bitmap fonts: S18RM04P.DAT (18px), S20RM04P.DAT (20px), S24RM04P.DAT (24px), S26RM04P.DAT (26px).

The DreamPassport browser engine renders Latin text (ASCII + ISO-8859-1) natively — accented Catalan characters should render without font hacking. Verify in emulator before investing in glyph work.

## Translation approach

1. Extract `STORY.PAC` and find all Shift-JIS text blocks (hiragana/katakana sequences)
2. Build offset table: `(offset, length, original_text)`
3. Translate in place (Shift-JIS → UTF-8 → Catalan → ASCII/Latin-1 for reinsertion)
4. Reinsert at same offsets — Latin text is 1 byte/char vs 2 bytes/char Japanese, so strings will be shorter and fit comfortably
5. Edit `DPETC/MESSAGE.INI` for UI strings
6. Repack disc: rebuild ISO, create new GDI

## Space constraint

Japanese Shift-JIS dialogue uses 2 bytes per character. Catalan/Latin uses 1 byte per character. Same byte budget = roughly 2x the character count available. Space is not a constraint.

## Proven path

All text files are human-readable (Shift-JIS or HTML-like). No custom encoding table needed. No font hacking required for Latin scripts. Most accessible DC translation target identified.

---

## Implementation & Per-Game Guides

**Extraction code**: [`pluto/api/modules/translation/dc/extract.py`](../../../api/modules/translation/dc/extract.py)

Per-game notes:
- [`games/boku-doraemon.md`](./games/boku-doraemon.md) — 60% extraction working, speaker tag pattern proven
