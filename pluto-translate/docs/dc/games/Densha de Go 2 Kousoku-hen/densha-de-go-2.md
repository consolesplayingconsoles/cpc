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

- header low byte & 0x7F = width in tiles, bit 7 = a flag not yet understood, high byte = height in tiles;
- then width x height u16 tile ids, row by row.

Tiles are 16x16, 256 per 256x256 texture, row-major: tile id → texture `id // 256`, x `(id % 16) * 16`,
y `(id % 256 // 16) * 16`. `TBL.ROM` ids index `CG1.ROM` (highest id 22764, 89 textures = 22784 tiles),
`VQ_TBL.ROM` ids index `VQ_CG.ROM` (highest 33387, 131 textures = 33536). Every one of the 2417 records fits
this layout. Tiles are deduplicated, so a texture on its own looks like shredded strips: render the record,
not the texture.

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

`OBJz_menuber0-3` are a background pattern, not menu text. The header legend (メインメニュー, 選択,
キャンセル, 決定) is in another record; not found yet.
