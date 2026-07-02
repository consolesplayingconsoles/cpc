# Boku Doraemon (Català) — bug / task tracker

Living list so nothing gets lost. Status: 🔴 open · 🟢 fixed in code (awaiting build) · ✅ confirmed on DC · ⚪ later.

## Font / text (`pluto-translate/dc/fon_codec.py`)

- 🟢 **Enclitic apostrophes** — this game renders a RIGHT-edge apostrophe (M'/S') but NOT a left one.
  So an enclitic's apostrophe belongs to the PRECEDING vowel as a right-apostrophe: `canvia't` =
  `canvi` + `a'` + `t`. Added `a' e' i' o' u'` combos (`_CSPEC`); `fw` matches them automatically. The
  dead `_apos_l` left-apostrophe path is removed. Unit tests: `dc/test_fon_codec.py`.
- 🟢 **Ellipsis `...` first dot cut off** — dots moved to cols 5/10/15 (first clear of the left edge).
- 🟢 **M' ghost "|" bar** — orphan col-0 serif dropped after the squeeze.
- 🟢 **Nobita/Doraemon face emojis removed** — now plain text (operator handles overflow by hand).
- 🟢 **`_MENU` (A:sí/B:no) + sí/no combo glyphs** — deleted (unused; switched to S/N text-side).

## Textures (repaint scripts under `games/Boku Doraemon/`)

- 🟢 **Invention / item names overflow one line** — `DOUGU_ITEMTBL.PAC` now packs with `box=20`
  (`build_patch.py` PLAN), so entries >20 chars wrap to 2 lines via the `01 ff` break; shorter gadget
  names stay one line. Tune the width if a 1-line label anywhere wraps.
- 🔴 **Save prompt still JP** — `ここで セーブしますか？ / Aボタン（はい）／Bボタン（いいえ）`
  → "Vols desar aquí? / Botó A (sí) / Botó B (no)".
- 🔴 **In-game action menu still JP** — `いどう / ポケット / じょうほう / オプション`
  → `Anar / Butxaca / Informació / Opcions`.
- 🔴 **More menus/titles than expected** — sweep pass needed; add each here as found.
- 🟢 **MN mini-game counter** — `ドラやき`→`PASTISSETS`, `ゲット数`→`GUANYATS`.
- ⚪ Mini-game tutorial (`そうさ方法`) still JP.
- ⚪ Race flashes (`用意 / スタート / 終了` → Preparats / Ja! / Fi!) still JP.

## Pluto app (Vue)

- 🟢 **Scene index off-by-one** — the header showed `scene + 1` (index 36 appeared as 37), which is
  why referencing a scene by number hit the wrong one. Now shows the raw 0-based `scene` id
  (`TranslationTable.vue:1136`). The server order-sort itself is stable/correct.

## Deferred
- Sync confirmed gadget names into `DOUGU/ITEMTBL.PAC` (beta phase).
