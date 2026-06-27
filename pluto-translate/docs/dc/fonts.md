# Dreamcast Fonts — cracking & extending `S18RM04.FON`

The font is the universal wall in Dreamcast fan-translation: Japanese games ship an
**SJIS-only** font with **no half-width Latin and no accented glyphs**, so any Latin
language that needs `à é ç …` (Catalan, French, Spanish, Portuguese, German) hits it.
This is what stalled SEGAGAGA. Solved here for `S18RM04.FON`; the method generalizes.

Code: [`../../dc/fon_codec.py`](../../dc/fon_codec.py) (codec + accent authoring + `fw()` text encoder).
Per-game patched fonts are **derived artifacts** — regenerate, don't commit:
`python3 fon_codec.py <orig.FON> <patched.FON>`.

## Format (cracked 2026-06-27)

`S18RM04.FON` is a flat array of **106-byte records**, one per glyph, in JIS row-major
order (record `idx = (jis_hi-0x21)*94 + (jis_lo-0x21)`):

| bytes | meaning |
|---|---|
| `[0:2]` | JIS code, **byte-swapped** (`41 23` = JIS `2341` = full-width 'A') |
| `[2:10]` | per-glyph header (bounding box / padding — copy as-is when authoring) |
| `[10:106]` | **2bpp bitmap, width 20** (5 bytes/row, MSB-first, palette 0..3), 19 rows |

It is *plain linear 2bpp* — not compressed/vector (an earlier wrong read). The crack
came from **yzb's CrystalTile2 params**: tile **width 20**, payload **offset +10**.
Verify any glyph by rendering record `idx*106 + 10` at 2bpp/20px (`fon_codec.decode`).

## Accents — the Greek-slot trick

SJIS can't even *encode* `à`, and the font has no glyph for it. So:

1. **Pick dead slots:** a Japanese game never renders **Greek** (`SJIS 0x839F–0x83D6`).
   Confirm per game by scanning the text for codes in that range; record the count in the game's doc.
2. **Author glyphs:** copy the base letter's record, overlay the accent mark in the
   empty rows of its 2bpp grid (grave/acute at top, dieresis dots, cedilla tail at
   bottom; clear the i-dot for `í`/`ï`), set the record's JIS code to the Greek slot,
   write it there. `build_patched_font()` does all 20 (à è é í ï ò ó ú ü ç + uppercase).
3. **Encode text to the slots:** `fw()` maps each accented char → its Greek SJIS code,
   so patched text + patched font line up. Codec-free (no `shift_jis` needed on Batocera).

## Caveats / TODO
- Uppercase accents are tight (caps fill rows ~3-18, mark squeezed into 0-2) — readable, tunable.
- `ŀl` (middot) has no glyph yet — `fw()` folds `l·l → ll`. Author a `·` glyph later if wanted.
- Accent-mark pixel positions are hand-drawn; refine against on-screen rendering.

## Reuse
The format + the Greek-slot method carry to **other games using this font** and to
**other accented languages** (just change the `ACCENT_SPEC` char set). Different DC
font (other dimensions)? Re-crack width/offset with CrystalTile2, keep the method.
See also the texture path for baked-in menu/title art: [`textures.md`](textures.md) + `../../dc/pvr_codec.py`.
