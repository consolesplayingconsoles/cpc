# Densha de Go! 2 Kousoku-hen 3000 (電車でGO!2 高速編 3000番台) — Dreamcast (1999)

Translation target: **Japanese → English**, carrying over Zoinkity's English from Densha de Go! 64 (N64) where
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

| # | Japanese | Taito's English | DDG64 (Zoinkity) |
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

Done 2026-09-29 by `repaint_mainmenu.py` (Taito's wording, Arial Narrow Bold, grey 189 on 8): 543 unique tiles,
144 kept as they were, 399 rewritten, 44 slots spare. Only `OBJz_mainmenu` and `CG1.ROM` 86-88 change; every
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
3. **Wording first from the game, then from DDG64.** Taito put small English on some DC buttons; Zoinkity's
   DDG64 set covers most shared screens. Coin only what neither has, and log it in the workbench `FLAGS.md`.
4. **Erasing by colour needs a flat background.** Replacing grey pixels with the black worked on the menu's flat
   black. Text with a drop shadow over the patterned "3000" background (Game Setting, Load/Save) needs the
   background rebuilt from a clean copy, not a colour fill.
5. **Verify three ways, every time:** the repaint re-rendered from the OUTPUT files equals the preview; every other
   record renders byte-identical; the files read back from the patched track equal the outputs.
6. **Disc:** `inplace.py` per file (same size, no rebuild), as for Boku.
7. **Flagged records (`CG2.ROM`) are a different repaint.** No texture to redraw: re-tile, compress each new
   tile, rewrite the record's ids. Every one of the 17396 slots is used and the file has 89 spare bytes, so new
   tiles take the ids the old Japanese tiles free (only tiles no other record uses; tile 0 is the blank shared by
   all), and the rebuilt `CG2.ROM` must fit the original size: that needs a compressor at least as tight as
   Taito's. Draw with the index values the original text and shadow use, so the record's unknown palette does
   not matter.

## Screens and their DDG64 counterparts

Seen in game 2026-09-29 (screenshots in the workbench `reference/`). Numbers are Zoinkity's `007gg4` files.

| Screen | Japanese | DDG64 match |
|---|---|---|
| Header legend (every screen) | 選択 / キャンセル / 決定 | "Select: + Pad / Decide: A Button" (`686-689`), "Back / Choose" (`871`). Cancel is not there |
| Route select header | 路線選択 | "Route Select" (`868`), different style |
| Route select groups | 北陸路線 / 東北路線 / 関東路線 | none: DDG64 names each line (`690-697`), the DC groups by region |
| Game Setting header | ゲーム設定 | "Options" (`1031`) |
| Game Setting items | コントロール, 難易度, 振動, サウンド, 速度メーター, 距離メーター | Controls, Difficulty, Sound, Speedometer, Distances (`1032-1036`); 振動 (Vibration) is DC only |
| Game Setting values | ツーハンドルA, ノーマル, 並, ステレオ, ノーマル, m 表示 | Two-Handed A/B, One-Handed, Train Controller, Easy/Normal/Hard/Very Hard, Stereo/Mono, Normal/Digital, Meters (`1038-1062`); 並 (vibration strength) is DC only |
| Ranking | 秋田新幹線, E3系, 次に進む, メニューに戻る | "Akita Shinkansen" (`697`), "E3 Series" (`722`), "(A) Next" (`728`), "(B) Main Menu" (`729`) |
| Load/Save | ロード・セーブ, ロードする, セーブする | none (Controller Pak strings only: "DATA SAVING", "Now Saving...") |

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

`ddg_assets.py sheets` draws every record on named contact sheets; filter on the bit to see only the clean ones.
