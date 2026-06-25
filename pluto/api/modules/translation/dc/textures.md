# Translating baked-in text (PVR textures) — Dreamcast

Some on-screen text is **not** a string in a file — it's drawn as a **PVR texture**
(title menus, logos, pre-rendered screens). You can't patch a string that doesn't
exist; you edit the image. This is the proven method (done for Boku Doraemon's
title menu: はじめから/つづきから/オプション/インターネット → COMENÇA/CONTINUA/OPCIONS/INTERNET).

Dividing line: **editable text → patch the bytes** (see `extract.md`); **pixel
text → this doc.** Reusable codec: [`pvr_codec.py`](pvr_codec.py).

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
