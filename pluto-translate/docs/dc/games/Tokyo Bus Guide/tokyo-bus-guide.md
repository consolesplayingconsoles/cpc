# Tokyo Bus Guide (東京バス案内) — Dreamcast (1999)

Translation target: **Japanese → English**

## Game

Bus-driving simulator by Fortyfive / Sunsoft. You drive Toei Bus routes through
Tokyo to a timetable, scored on stops, signals, announcements and passenger
comfort. Japan-only.

Console guide: `../../extract.md`

## Where the knowledge came from

Unusually, this game has a **public decompilation**
([lhsazevedo/tokyo-bus-guide-decomp](https://github.com/lhsazevedo/tokyo-bus-guide-decomp),
the first for any Dreamcast title). Everything below was read out of C source
rather than recovered by scanning bytes.

The decomp is submoduled on the modding side, with the symbol map and navigation
notes: `nodes/local/dc/homebrew/mods/tokyo-bus-guide/`. Read that for *where
things are in the code*; read this for *how to translate them*.

## Text sources

Two surfaces, two techniques.

| Surface | Where | Technique |
|---|---|---|
| Menu / course labels | `\SYSTEM\menu.pvm` (+ `title.pvm`, `common.pvm`) | PVR repaint (`../../textures.md`) |
| Instructor dialogue | `1ST_READ.BIN` | **done**: rebuilt from the decomp, no byte limit |
| Save / VM menu strings | `1ST_READ.BIN` | **done**: same |
| Chat while driving | `*_TEXT.DAT` (21 files) | `tbgtext` parser + packer, grows the file |

The executable surfaces are already translated, and not by patching bytes: the game
is rebuilt from lhsazevedo's decompilation, so a string may be any length. See
`nodes/local/dc/homebrew/mods/tokyo-bus-guide` in `dreamcast-homebrew`. Lines still
have to fit the on-screen box: **22 full-width characters per line, 2 lines**.

Menu labels are **sprites, not strings**: the engine draws them with
`TxtDrawSprite(group, texture_id, x, y, priority)`, so "Story", "Free Run",
"Option" and "VM Game" are pixels. Course entries carry a `spriteNo` too.

The dialogue is the opposite: 133 Shift-JIS literals sit in the executable as
`{char *text, int portrait}` arrays (the whole instructor script), plus 9 more in
the VM save menu. Those are translated in the decomp source itself.

### Chat while driving: `*_TEXT.DAT`

The passengers' conversations, three files per area (`S_`, `W_`, `O_`), all
little-endian:

    [u32 scene table]   first entry = the table's own size, so count = first // 4;
                        each entry points into the pair area
    [pair area]         (u32 textOffset, u32 id) records; a scene is a run of them
                        ending in one whose id is 0x7fffffff and whose text is empty
    [strings]           NUL-terminated Shift-JIS, 4-aligned, `<E>` = line break

`id` is a voice id, except in `SYSTEM/S_TEXT.DAT` where the second field is a second
line. The 21 files on the disc repeat across areas, so they hold only **1,292
distinct lines** (~26,000 characters).

`parsers/tbgtext.py` reads them and `packers/tbgtext.py` writes them back by index
rewrite: the scene table and pair area keep their size, the strings are re-emitted and
every pointer is repointed, so English can be longer. All 21 files round-trip
byte-identically when nothing is translated.

## Resource group format

This is Ninja/Shinobi SDK layout and is likely to recur on other Dreamcast
titles, so it is worth knowing generally. A resource group is three files in
`\SYSTEM` plus an id:

```c
{ "menu_parts.dat", "menu.dat", "menu.pvm", 3 }
```

* **`<name>.dat`** — u32 offset table indexed by `texture_id`. Each entry points
  at a `{sprite_no, x, y}` list terminated by `sprite_no == -1`, so one
  `texture_id` composites several sprite pieces at relative offsets.
* **`<name>_parts.dat`** — the `NJS_TEXANIM` array: per-sprite width, height and
  UV rect.
* **`<name>.pvm`** — the texture archive.

Groups: `common`, `title`, `menu`, `practice01`, `practice02`.

### Why this matters for repainting

On Boku Doraemon the recurring bug was **overflow**: the engine maps a label to a
screen quad narrower than its atlas box, so text drawn to the box edge clipped on
hardware. It was found by eye on a screenshot after the fact and worked around
with a hand-tuned `fill` fraction per label (see `repaint_option1.py`).

Here `_parts.dat` *is* the quad table, so the true extent is readable before you
draw anything. And because it is a small same-size data file, a **wider** label
may be reachable by editing the UV rect instead of compressing the wording.
Unverified, worth testing early: it decides how tight the translation has to be.

## Font

`\SYSTEM\bus_font.fff`. Glyphs are 24x32, 2 bits per pixel, `0xC0` bytes each,
unpacked and twiddled to ARGB1555 at runtime.

**Latin glyphs already exist.** The font's section table runs: special, digits and
Roman (`0x006C`), hiragana, katakana, Greek (`0x0153`), Cyrillic (`0x0183`), then
32 kanji sets. So unlike Doraemon (whose glyph atlas had to be rebuilt by
`fon_codec.py`) a Latin-script translation may need no font patch at all. Confirm
against the accented characters you actually need before relying on it.

Text is two bytes per character (Shift-JIS) with three-byte tags: `<E>` line
break, `<C>` / `<D>` / `<R>` set the palette (`<R>` draws red).

## Plan: the main menu

Goal is the four items on the first screen, enough to navigate in a language you
read.

1. **Extract and inventory.** Keep `menu.pvm`, `menu.dat`, `menu_parts.dat`. Walk
   the PVM with `pvr_codec.find_chunk` for `(offset, w, h, pixfmt)` per chunk.
2. **Identify the label chunk by content, not index.** Chunk order is not stable
   in this engine family; indexing by position gave wrong answers twice on
   Doraemon.
3. **Check the pixel format first.** ARGB4444 round-trips byte-exactly through
   `pvr_codec`. **ARGB1555 does not** — re-encode only changed pixels into the
   original buffer or you re-quantise the whole atlas.
4. **Map ids to rects.** The menu draws ids `0x64`, `0x65 + offset` and `0x2d`.
   Resolve each through `menu.dat` to its sprite list, then each `sprite_no`
   through `menu_parts.dat` to a UV rect. That is the real per-label box.
5. **Repaint.** New script in `dc/games/Tokyo Bus Guide/`, modelled on
   `repaint_option1.py`.
6. **Commit the texture, then build.** Repainted textures are the source of truth
   in the game's committed `textures/` dir; the Lab API serves them as a tar and
   `translate.sh` splices them in place.

### Pipeline blockers to clear first

(The texture splice's case-sensitive globs are fine here: the filenames on the disc
are uppercase, as Doraemon's are. The lowercase names in the decomp sources are how
the code spells them, not how they are stored.)

**`build_patch.py`'s `PLAN` is Doraemon-only.** A source with no `PLAN` entry is
skipped silently, so this game currently produces no patched files at all.

**The splice targets `track05.bin` by name.** If this game's data track is
numbered differently, every splice fails cleanly and you get an unpatched disc
plus a `DONE:` line.

(The hardcoded `S18RM04.FON` font step was the same class of bug and is fixed:
it now skips when the disc has no such file.)

### What is left

The executable text is done. What remains is the chat while driving (1,292 lines,
tooling ready) and the menu/course labels, which are pixels and need a repaint
script.

## Gotcha: reading the decomp sources

`016d2c_course_menu.c` and `0193c8_vm_menu.c` contain raw Shift-JIS. macOS `grep`
in a UTF-8 locale treats the `0x85` byte as a line terminator and silently returns
**nothing** on those files. Use `LC_ALL=C`, or read them in Python with
`open(f, "rb")` and decode as `shift_jis`.
