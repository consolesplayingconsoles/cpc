# Densha de Go! 2 Kousoku-hen 3000 (電車でGO!2 高速編 3000番台) — Dreamcast (1999)

Translation target: **Japanese → English**, carrying over the English of Densha de Go! 64 (N64; Zoinkity and mikeryan) where
the screens match. Status: menus first, so you can navigate the game and find the next target.

Disc: `T-1102M`, `V1.001`, `19991212`. Console guide: `../../extract.md`. Texture method: `../../textures.md`.
Tool: `pluto-translate/dc/games/Densha de Go 2 Kousoku-hen/ddg_assets.py`. Workbench (reference images,
repaints): `translations/dc/Densha de Go! 2 Kousoku-hen (Japan) [en]/`.

## No text, only textures

A Shift-JIS scan of every file finds nothing but binary noise (and the developers' comments in `EFFECT.OUT`).
Every on-screen word is baked into a texture, so there is no state.json text to extract: the whole translation
is the repaint path.

The game runs on Windows CE: `0WINCEOS.BIN` boots `DENGO3K.EXE`, with 50 `WINCE/*.DLL`. Code patches would
mean PE/SH4 on WinCE, not Katana.

## Disc layout

| File | Format | Holds |
|---|---|---|
| `CG1.ROM` | ROM2, 89 PVRT 256x256 (86 VQ, 3 ARGB1555 twiddled) | 2D art for `TBL.ROM` sprites: menus, speedometers, photos |
| `VQ_CG.ROM` | ROM2, 131 PVRT VQ 256x256, ARGB1555 codebook | 2D art for `VQ_TBL.ROM` sprites: HUD, messages, station names, staff roll |
| `TBL.ROM` | ROM2, 1252 sprite records | tilemaps into `CG1.ROM`; named by `SPRITE.LST` |
| `VQ_TBL.ROM` | ROM2, 1165 sprite records | tilemaps into `VQ_CG.ROM`; named by `TBL.OUT` |
| `CG.ROM` | ROM2, 2099 entries starting `00 10 00 00`, 128 to 4097 bytes | looks compressed. Not decoded |
| `CG2.ROM` | not ROM2 | not decoded |
| `<ROUTE><n><x>.COM` / `.RIL` | `RAIL DATA VER7.0` / compressed | per-route data, indexed by `RAIL.ROM` |

Routes on the disc: `AKITA` (Akita Shinkansen), `HOKUHO` (Hokuhoku), `KEIHIN` (Keihin-Tohoku), `TOUKAI`
(Tokaido), `YAMATE` (Yamanote). Densha de Go! 64 has all five, plus routes this disc lacks.

**ROM2**: u32 `ROM2`, u32 count, then count x (u32 offset, u32 size) from the file start.

**Dev listings**: `SPRITE.LST` is the developers' C listing of `TBL.ROM`, `OBJname, /* offset, size */`, one
line per record, and matches it exactly (1252 of 1252). `TBL.OUT` lists `VQ_TBL.ROM`'s 1165 records in the same
order but from an older build (every size 2 bytes larger), so use its names by index only. `EFFECT.LST` is a C
`effect_table[]`.

## Sprites are tilemaps

A sprite record is a u16 header then tile ids:

- header low byte & 0x7F = width in tiles, bit 7 = tile source (below), high byte = height in tiles;
- then width x height u16 tile ids, row by row.

Tiles are 16x16, 256 per 256x256 texture, row-major: tile id → texture `id // 256`, x `(id % 16) * 16`,
y `(id % 256 // 16) * 16`. `TBL.ROM` ids index `CG1.ROM` (highest id 22764, 89 textures = 22784 tiles),
`VQ_TBL.ROM` ids index `VQ_CG.ROM` (highest 33387, 131 textures = 33536). Every one of the 2417 records fits
this layout.

**Header bit 7 = the tiles come from `CG2.ROM`, not `CG1.ROM`.** 299 `TBL.ROM` records have it clear and render
cleanly from `CG1.ROM`; 953 have it set and render as garbage from `CG1.ROM`. `VQ_TBL.ROM` never sets it.

- `CG2.ROM` = u32 count (17396), then that many u32 offsets, then one compressed 16x16 tile per entry (5 to 278
  bytes). Highest flagged tile id is 17272, so the ids fit.
- An entry is a type byte then a stream of controls, decoding to 256 palette indices, row-major 16x16.
  `c >= 0x80`: copy the next (c & 0x7F)+1 bytes as they are. `c < 0x80`, **type 1**: repeat the next byte c+1
  times (run-length). `c < 0x80`, **type 2**: copy c+1 bytes from (next byte + 1) back in the output (LZ77;
  distance 1 repeats the last pixel). 2220 tiles are type 1, 15176 type 2; all decode to exactly 256.
  `ddg_assets.cg2_decode`.
- Cracked 2026-09-29 against ground truth: 868 flagged records have a same-shaped twin in `VQ_TBL.ROM` (names
  from `TBL.OUT` by index) that renders cleanly. Uniform tiles line up 12331 to 5; decoded tiles match their
  twin's colours (the misses are VQ's own loss). Worth remembering: a first guess (every control below 0x80 is a
  run) also summed to 256 on every tile and was wrong for type 2. Summing right is not proof; the twins are.
- `PAL.DAT` = 52 palettes of 256 ARGB1555 colours (512 bytes each). Palette 1 is the UI palette (0 transparent,
  1 black, 7 white, 10 yellow, 15 red) and matches the twins. Which palette a record uses is not in the record,
  so some records draw in odd colours with palette 1 (the grey section headers come out white and yellow). A
  repaint does not need the palette: it reuses the index values the original's text and shadow already use.

Tiles are deduplicated, so a texture on its own looks like shredded strips: render the record, not the texture.

```
ddg_assets.py render SPRITE.LST TBL.ROM CG1.ROM OBJz_mainmenu mainmenu.png
```

## Main menu

`OBJz_mainmenu`: 32x30 tiles (512x480), five 96-pixel buttons, each with Taito's own small English under the
Japanese:

| # | Japanese | Taito's English | DDG64 |
|---|---|---|---|
| 1 | アーケードモード | Arcade Mode | Arcade Mode (`1019`) |
| 2 | ゲーム設定 | Game Setting | Options (`1021`) |
| 3 | ランキングを見る | Ranking | Rankings (`1022`) |
| 4 | ロード・セーブ | Load And Save | (none) |
| 5 | LOVE特急こまち | Love Express Komachi | (none, DC only) |

DDG64's menu (`007gg4/1019-1023`, 256x45 strips) has the same design: number, coloured bar, label.

Repaint facts: the menu's 960 tile positions use 568 unique tiles, all in `CG1.ROM` entries 86-88, which are
the three plain ARGB1555 twiddled textures (not VQ), so they encode exactly. No other record uses those tiles.
Free slots in 86-88: 19 (all in 88). A repaint re-tiles the new 512x480 picture, deduplicates, writes the
tiles into the menu's own slots, and rewrites `OBJz_mainmenu`'s ids in place (same size).

Done 2026-09-29 by `repaint_mainmenu.py`: buttons 1-3 in the DDG64 English (1019, 1021, 1022), buttons 4-5
left as the original art (no DDG64 match); Arial Narrow Bold, grey 189 on 8. 509 unique tiles, 321 kept as they
were, 188 rewritten, 78 slots spare. Only `OBJz_mainmenu` and `CG1.ROM` 86-88 change; every
other record renders byte-identical. The patched `CG1.ROM` / `TBL.ROM` sit in the workbench `textures/` and go
onto the disc with `inplace.py` (same size, no rebuild). Tested in Flycast 2026-09-29: works.

`OBJz_menuber0-3` are a background pattern, not menu text. The header legend (メインメニュー, 選択,
キャンセル, 決定) is in another record; not found yet.

## Method: how to do the next screen

Lessons from the main menu. Read this before starting a screen.

1. **Find the record, render it, never read a texture directly.** Textures are deduplicated tile pools and look
   shredded. `ddg_assets.py render` (or a contact sheet of every record) shows the screen as the player sees it.
2. **Triage before painting.** For the record's tiles, find: which textures (plain ARGB1555 twiddled in `CG1.ROM`
   86-88 encodes exactly; VQ does not, it needs a new codebook), whether any other record shares them, and how
   many free slots those textures have. Main menu: plain, unshared, 19 free = the easy case.
3. **Wording is DDG64's only (a port, cpc `CLAUDE.md` section 11).** A label gets English only when DDG64 has
   the same Japanese (match by texture number); otherwise it stays the original art and goes on the gap list in
   the workbench `TRANSLATION.md` (its working notes). Never Taito's small English; a gap stays Japanese unless cpc
   words it (listed in the same file).
4. **Erasing by colour needs a flat background.** Replacing grey pixels with the black worked on the menu's flat
   black. Text with a drop shadow over the patterned "3000" background (Game Setting, Load/Save) needs the
   background rebuilt from a clean copy, not a colour fill.
5. **Verify three ways, every time:** the repaint re-rendered from the OUTPUT files equals the preview; every other
   record renders byte-identical; the files read back from the patched track equal the outputs.
6. **Disc:** `inplace.py` per file (same size, no rebuild), as for Boku.
7. **Flagged records (`CG2.ROM`) are a different repaint** (`repaint_cg2.py` is the template). No texture to redraw: re-tile, compress each new
   tile, rewrite the record's ids. Every one of the 17396 slots is used and the file has 89 spare bytes, so new
   tiles take the ids the old Japanese tiles free (only tiles no other record uses; tile 0 is the blank shared by
   all), and the rebuilt `CG2.ROM` must fit the original size: that needs a compressor at least as tight as
   Taito's. Draw with the index values the original text and shadow use, so the record's unknown palette does
   not matter.

## Screens and their DDG64 counterparts

This is a port (cpc `CLAUDE.md` section 11): English only where DDG64 has the same Japanese, matched by
texture number (`mld82r/Images/<n>.bin.png` Japanese vs `007gg4/<n>.bin.png` English). The authoritative table
(every ported string with its texture number) and the gap list are in the workbench `TRANSLATION.md` (its working notes); the scripts carry
the same numbers next to each string.

Find a match by rendering both sets side by side by number, never from contact sheets with labels under the
images: that is how 686-689, 728-729 and 871 got misread here once (the legend is really 870, the Ranking footer
738-741). Useful ranges: main menu 1019-1023, options 1031-1061, Route/Train Select 868-869, legend 870-871,
Ranking footer 738-741, pause 878-879.

## Which records the screens use (found 2026-09-29)

Clean, `CG1.ROM`, repaintable now:

- `OBJtopl01-07` line banners (田沢湖線, 東海道本線, 京浜東北線, ほくほく線, 奥羽本線, 秋田新幹線, 山手線) and `OBJtopr01-11`
  series banners (209系 ... HK-100形): the Ranking screen header is one of each (秋田新幹線 + E3系).
- `OBJtop09` 乗務記録, `OBJtop10` "選択：ブレーキ / 決定：スタートボタン".
- `OBJstart*` departure-board signs (stations, 快速, 普通, series), `OBJtuuti01` the 運転評価 score card.
- `OBJz_haikei` = the clean "3000" background tile behind Game Setting and Load/Save.
- Train fronts on Route select are `OBJ200`-`OBJ701b` (pictures, no text).

Flagged (`CG2.ROM`), found with the codec:

| Record | Holds |
|---|---|
| `OBJz_submenu`, `OBJz_submenu2` | the section headers: メインメニュー, ゲーム設定, ロード・セーブ, 路線選択, 電車選択, the Game Setting item names, ロードする / セーブする |
| `OBJz_font`, `OBJz_font2` | Game Setting items and every value (ツーハンドルA-D, ワンハンドルA/B, 専用コントローラ, イージー ... ベリーハード, 切弱並強, ステレオ/モノラル, 非表示 / cm 表示 / m 表示 / デカデジ, ポートA/B拡張ソケット1), two styles (normal, highlighted) |
| `OBJz_kettei` | legend: 選択, キャンセル, 決定, おわり |
| `OBJz_ranking`, `OBJz_ranking2` | Ranking footer: (A) 次に進む, (B) メニューに戻る; and the B/C variant |
| `OBJexsel01` group | route select regions: 北陸路線, 東北路線, 関東路線 |
| `OBJpret01` | a chrome 路線選択 header |
| `OBJz_pause` | pause menu (運転再開, 運転中止, 始発駅に戻る, 画面位置調整) |
| `OBJz_mes*` | memory card messages |
| `OBJsou*` | route diagrams with station names |

`ddg_assets.py sheets` draws every record on named contact sheets (pass `CG2.ROM PAL.DAT` to include the
flagged ones).

## Section screens (CG2 repaint)

Done 2026-09-29 by `repaint_cg2.py`, on top of the main menu's `TBL.ROM`. Records: `OBJz_submenu`,
`OBJz_submenu2` (headers, 48-pixel bands, fill 92, antialiasing 91/90/89, no shadow: the engine adds one),
`OBJz_kettei` (legend, 32-pixel bands, fill 7, 78/77/4), `OBJz_font` / `OBJz_font2` (Game Setting items and values,
32-pixel bands in two columns, fill 92 / 90, antialiasing 91-90-89 / 89-93-94, hard shadow index 88 at +3,+3),
`OBJz_ranking` / `OBJz_ranking2` (footer, fill 6, antialiasing 4/5, shadow 3 at +3,+3; the button icons at x 1-30
and 161-190 stay). The game draws each label as its own box sized to the Japanese, so every English label stays
inside its Japanese label's extent (squeezed to 80%, then scaled down). Gap labels are left byte-identical.

- 1159 tile ids freed, 494 kept (gap labels, shared shapes), 663 new, 2 spare: close to the limit. The next CG2
  batch may have to take ids from records it repaints with gaps turned to blanks, or free more.
- The English needs more bytes than the Japanese: recompressing 1280 other tiles (each checked to decode to the
  same pixels) reclaimed 8651 bytes; 912 to spare.
- Checks: every repainted record re-read from the outputs equals its preview; every other record is unchanged;
  every gap label is identical to the original; the three files read back from the patched track equal the
  outputs. Before a test build, list per screen what should read English and what stays Japanese.

Tools in the translate API (`pluto-translate/openapi.yaml`): `GET /files?path=<gdi>` lists the data track's files
without an extract (`dc/gdi_files.py`, stdlib); `GET /sprites?path=<gdi>` lists every record of both tables;
`GET /sprite?path=<gdi>&name=<OBJ>[&table=VQ_TBL][&palette=N]` renders one as base64 PNG. The sprite tools need
numpy + PIL in the interpreter serving the API.
