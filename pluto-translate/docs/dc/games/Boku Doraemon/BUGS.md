# Boku Doraemon (Català) — bug / task tracker

Living list so nothing gets lost. Status: 🔴 open · 🟢 fixed in code (awaiting build) · ✅ confirmed on DC · ⚪ later.

## Font / text (`pluto-translate/dc/fon_codec.py`)

- 🔴 **Enclitic apostrophes render on the wrong side** (`canvia't`→`canviat'`, `te'n`→`ten'`).
  Root cause: Bug in code. Claude is stubborn and looking everywhere else.
- 🔴 **Ellipsis `...` first dot cut off on the left** — move the 3 dots slightly closer / off the edge.
- 🟢 **M' ghost "|" bar** — orphan col-0 serif dropped after the squeeze.
- 🟢 **Nobita/Doraemon face emojis removed** — now plain text (operator handles overflow by hand).
- 🟢 **`_MENU` (A:sí/B:no) + sí/no combo glyphs** — deleted (unused; switched to S/N text-side).

## Textures (repaint scripts under `games/Boku Doraemon/`)

- 🔴 **Invention / item names overflow one line** — need to wrap to **2 lines** (e.g. "Tauler de les
  bones opcions", "El ciment de la determinació" get cut).
- 🔴 **Save prompt still JP** — `ここで セーブしますか？ / Aボタン（はい）／Bボタン（いいえ）`
  → "Vols desar aquí? / Botó A (sí) / Botó B (no)".
- 🔴 **In-game action menu still JP** — `いどう / ポケット / じょうほう / オプション`
  → `Anar / Butxaca / Informació / Opcions`.
- 🔴 **More menus/titles than expected** — sweep pass needed; add each here as found.
- 🟢 **MN mini-game counter** — `ドラやき`→`PASTISSETS`, `ゲット数`→`GUANYATS`.
- ⚪ Mini-game tutorial (`そうさ方法`) still JP.
- ⚪ Race flashes (`用意 / スタート / 終了` → Preparats / Ja! / Fi!) still JP.

## Pluto app (Vue)

- 🔴 **Scene sort / indexing bug** — saving a scene by number inserts the WRONG block (scene 2 = game
  index 36 / UI 37, but it adds the "galaxy" one and corrupts state). ID mismatch. Fix: render the
  **exact 0-based index** in the UI. Files: `pluto/src/components/TranslationTable.vue`, `TranslationRow.vue`.

## Deferred
- Sync confirmed gadget names into `DOUGU/ITEMTBL.PAC` (beta phase).
