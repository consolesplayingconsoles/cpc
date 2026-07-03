# Translating baked-in text (PVR textures) — Dreamcast

Some on-screen text is **not** a string in a file — it's drawn as a **PVR texture**
(title menus, logos, pre-rendered screens). You can't patch a string that doesn't
exist; you edit the image. This is the proven method (done for Boku Doraemon's
title menu: はじめから/つづきから/オプション/インターネット → COMENÇA/CONTINUA/OPCIONS/INTERNET,
and the **options screen `OPTION1.PVR`** 2026-06-28 → OPCIONS / SO / VELOCITAT / CANVI DE PÀGINA /
VEUS / MÚSICA / EFECTES / STEREO·MONO / OFF·ON / S·L / RÀPID·LENT, rainbow number scales kept
pixel-exact). **CJK→Catalan width is the recurring trap**: single-CJK toggles have no room for full
words — use universal short standards (`ON/OFF`, t-shirt `S/L` for 小/大, `STEREO`), exactly the
economical register the operator asked for. `OPTION4.PVR` is the box frame (no text); `MESWIN.PVM`
is 16×16 dialogue-border tiles (no text).

**`MN1/2/3.PVM` = the timed mini-game HUD/tutorial** (same UI over 3 backgrounds). Inspected 2026-06-28.
The dorayaki-counter chunk (256×256) is **byte-identical across all three** (md5 `1b8edd90`) → repaint once,
stamp into each. **Actually confirmed baked (verified on hardware 2026-07-03): only the dorayaki counter** —
ドラやき/ゲット数 → **PASTISSETS / GUANYATS** (gold/green, food icon kept; "guanyats" = *obtained*, shown as
"pastissets guanyats" when you win them after a game). **PAUSE, POINT, Perfect!, 0123456789 are already
Latin → leave untranslated.**

⚠️ **Correction.** An earlier note here claimed "COMPLETE 2026-06-28 — all HUD text baked (the three そうさ方法
tutorials, ready/go/finish flashes, all result + scold bubbles, timers)". That was an **unverified overclaim**:
a re-check on real hardware 2026-07-03 found the MN2 instruction box + timer, and MN1's instruction / result /
scold / race-flash / timer chunks, were **all still Japanese**. Don't trust that claim — verify each chunk.
Status now — **the whole MN1/2/3 HUD is Catalan** (done 2026-07-03, previews verified, not yet console-verified),
via two scripts on the committed textures:
- `repaint_mn_instr.py` — all three `〜そうさ方法〜` boxes → `~ Com es juga ~` + body (A red / B blue, MN3 also
  Y green), the `残りじかん…秒` timers → `Temps…s`, and MN1's `Ａボタン/Ｂボタン` legend → **Botó A / Botó B**.
  Board = per-row margin-median green refill; timer/legend on transparent bg = alpha erase. Chunk indices differ
  per file (MN1 box=2 timer=5; MN2/MN3 box+timer=3).
- `repaint_mn_dialog.py` — the 9 Mama speech bubbles (praise/scold, `ドラちゃん`→Doraemon, `ドラやき`→pastissets,
  portraits kept, auto-fit), the gold race flashes `用意して〜/スタート!!/終了〜!!` → **Llestos… / Ja!! / Fi!!**
  (yellow→orange gradient), and MN3's `この位置に/かたづけてね` → **Desa-ho / aquí** (gold, red → arrow kept).
- Only PAUSE / POINT / Perfect! / ○✕ / the number atlas stay original (already Latin / symbols).

The text lives in the per-file 512×512 ARGB4444 chunks; **index is NOT stable** (MN1 has 7 chunks, MN2/3 have 6),
and each file's chunks differ (MN1's timer sits with its strength gauge, MN2's timer sits under the box).
**Gotcha: identify the text chunk by content, not index, and restrict to TRANSPARENT ARGB4444** (mean alpha < 180)
— the opaque RGB565 *background* chunks (grass/beach) have gold-ish pixels that false-positive a "find the gold
text" check. Green-board text = fill (flat or board-gradient row-refill) + redraw; timer/flashes on transparent
bg = alpha erase + redraw; portraits/icons/gauges/PAUSE/POINT/Perfect!/numbers kept. Inventory in
`games/boku-doraemon-mn-hud.md` (which ALSO overclaims "complete" — read it as a text list, not a done-list).

Dividing line: **editable text → patch the bytes** (see `extract.md`); **pixel
text → this doc.** Reusable codec: [`pvr_codec.py`](../../dc/pvr_codec.py).

## 1. Confirm it's a texture, not a string
Search the extracted disc for the on-screen text as Shift-JIS bytes. If a label
you can SEE on screen appears in **zero** files (e.g. `つづきから` did), it's a
texture. (Some labels also sit in `1ST_READ.BIN` for *other* screens — that's a
red herring; the title buttons are the texture.)

## 2. Find the texture
Extract the GDI (GDIBuilder GUI, or `buildgdi -extract`). PVR images are `.PVR`;
a `.PVM` is a **PVMH container** of several `PVRT` chunks. Parse every PVR/PVM
header for **width × height + pixel format + data format** — the menu is a
**wide, short text atlas**. Header layout (after an optional `GBIX`):
`PVRT`(4) + dataSize(4) + pixfmt(1) + datafmt(1) + pad(2) + W(u16) + H(u16).
For Boku Doraemon the menu lives in **`TITLE.PVM` → the `press` chunk**
(256×256, **ARGB4444**, **TWIDDLED**). The PVMH header (first ~200 bytes) holds
the chunk filenames as ASCII (`title000`, `title001`, `title002`, `press`, `SEGATOYS`).

## 3. Decode to PNG (eyeball to find the right atlas)
Decode every chunk to PNG and look. Decode = **detwiddle + unpack pixel format**.
`pvr_codec.py` does ARGB4444 with numpy; a no-dependency version writes PNG via
`zlib` and decodes ARGB4444/ARGB1555/RGB565 directly. Twiddle (Morton): a pixel
`(x,y)` is stored at index `(twiddle(x) << 1) | twiddle(y)` where `twiddle` spreads
a value's bits into even positions. Pixel unpack:
- ARGB4444: 16-bit LE, A=12-15 R=8-11 G=4-7 B=0-3, scale 4-bit→8-bit by **×17**.
- ARGB1555: A=bit15, RGB 5-bit → ×255//31. RGB565: R5 G6 B5, A=255.

## 4. Edit (Pillow)
Decode the atlas → `PIL.Image` (RGBA). For each label:
1. **Detect the text band** from the alpha channel — rows where `alpha>threshold`
   are text; contiguous text rows = a band; within it the `x` extent + median RGB
   give the box and the colour.
2. **Erase** the band (paint transparent), **draw** the translation in the band's
   colour with a dark 1px outline (mimics the glow), **fit the font to the band**
   and **centre it within the ORIGINAL label's x-extent** — NOT full width / left
   aligned, or the on-screen quad clips the right edge and it's off-centre.
3. Catalan accents: full-width Latin (`ＣＡＴＡＬＡ`) renders; **single-byte ASCII does
   NOT** (the font has no Latin — shows dots). For textures you draw pixels so any
   glyph is fine, but match the original look.

## 5. Re-encode in place (same size) and repack
`encode_argb4444(rgba)` → bytes, **identical length** (256×256 ARGB4444 = 131072 B).
Overwrite at the chunk's pixel-data offset inside the PVM (`find_chunk` gives it).
Size unchanged → **no PVM header edits**, the container stays valid. Round-trip is
byte-identical, so an unedited region is provably untouched.

## 6. Rebuild + boot
The modified `TITLE.PVM` is **root-level** on the disc → GDIBuilder **"Rebuild
Patched GD-ROM"** (Original GDI + a Modified-files folder containing just the PVM
+ separate empty output dir + 2352 mode) → boot in **Flycast** (not OpenEMU).

## Gotchas
- **The hover/pulse is engine-side**, the texture is static: 1ST_READ.BIN scales +
  colour-modulates the selected quad per frame (`sin(time)`). Your edit inherits it
  for free — but leave a few px headroom so the scale-up doesn't clip, and note crisp
  hard edges *shimmer* under the pulse where the soft original blurred it.
- **Centre within the original label box** (step 4.2) or it clips/off-centres.
- **ARGB4444 round-trips exactly** (4-bit ×17 ⇄ >>4); other formats may not.
- **TWIDDLED** is the common case here; VQ/PAL formats need a codebook (not covered).
- Mirror of the codec/encoder also lives in memory `project_dc_translation_extraction.md`.
