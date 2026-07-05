# Boku Doraemon (Català) — bug / task tracker

Status: 🔴 open · 🟡 code/asset done, NOT verified in-game · 🟢 verified in-game · ⚪ later.
Work from this file. Update it as items move.

## Open — fix these first (in order)

### 3. VMU memory-card manager — investigated, mixed picture — 🟡 decision needed
Findings (2026-07-05):
- The DP manager sprite sheets `DPTEX/VMSPARTS.PVR` + `VMSPART2.PVR` (VMS = Visual Memory System) are
  **already ENGLISH**: all/load/copy/delete/back, expansion socket 1/2, exit, file info, up/down, A–D.
  Only 3 tiny JP labels remain on VMSPARTS: 総ファイル数 / 空きブロック数 / ブロック. Format = ARGB4444 **VQ**
  (dfmt 0x3) — a same-size repaint needs a VQ encoder (buildable on the Lab, real work).
- `DPTEX_ORIGINAL/` = Sega's swappable "original design" pack (README confirms), textures are **PAL8**
  (dfmt 0x7, need a BANK*.PVP palette) — the Japanese-look set. Which set the game loads is a `dp3.ini`
  toggle (not yet pinned down).
- The BIG Japanese labels seen on the actual screen (メモリーカード title, ポートＡ拡張ソケット, 空きNブロック,
  データN) are **NOT on either sprite sheet** and are not plain text in any game file or in `dc_boot.bin`.
  They look like the **Dreamcast BIOS file-manager** (firmware, invoked by the game) — which can't be
  translated by patching the game disc. NOT proven (the boot ROM stores its font/strings compressed), but
  that's the leading explanation.
**REGION TEST (operator insight 2026-07-05):** the DC memory-card manager is drawn by the **region-specific
BIOS**. Flycast is showing JP because it loads a **Japanese `dc_boot.bin`**; a PAL/US boot ROM renders the
same screen in English. So: on a PAL DC (the real target) these labels should already be English → likely a
NON-ISSUE. Definitive test = load a PAL/US `dc_boot.bin` in Flycast and reopen the screen. If it flips to
English, it's firmware (done, nothing to patch). If it STAYS Japanese, it's the `DPTEX_ORIGINAL` PAL8 game
textures and gets a repaint.
DECISION: pending the region test. Buttons are already English regardless. Don't build the VQ encoder until
the test says the labels are baked game art, not BIOS.

### 4. Choice/selection menu breaks on multiline — 🔴
A multiple choice renders garbled when the text wraps: `Te'l faré menjar` then a broken `sí … o` split
across lines. Locate the choice/prompt format (STORY.PAC control codes vs a separate table) and either
pack it single-line or lay out 2 lines properly.

## Done 2026-07-05 — code/asset done, pending a clean build + in-game check

- **VMU save/load DIALOGS** (`DPETC/MESSAGE.INI`) — 🟡 36 memory-card dialog strings (saving/loading/
  don't-remove-card/free-blocks/complete/cancelled/select-card/save-load prompts) → Catalan, ASCII-safe
  (DP font, no accents), "targeta"→"VMU" to save budget. New `packers/lines.py` (same-size, pad-to-budget),
  wired into `build_patch.py` + `translate.sh`. Packs 71371→71371 B. NOTE: this is the dialogs, NOT the
  manager-screen labels (those are textures — Open #3).
- 
- **Ela geminada `l·l`** — 🟡 root cause was a slot COLLISION: `0x83CA` was both `_ACCENTS["·"]` and the
  `il` digraph, so `·` rendered as "il". Moved middot to `0x83D1` + bolded to 4×4. Verified in the
  regenerated font. `fon_codec.py` pushed to box. Rebuild to confirm `col·lecció` shows the dot.
- **MN1 massage-minigame cursor** — 🟡 my legend erase wiped the yellow timing-bar cursor; fixed
  `repaint_mn_instr.py` to preserve yellow pixels, regenerated MN1/2/3.

## Rules (do not repeat these mistakes)
- **state.json writes:** get approval FIRST + re-fetch the latest state (operator edits live) + write with
  `ensure_ascii=False, indent=2` (match the app) + back up. Never write off a snapshot. I reformatted the
  whole file once with `indent=1` — do not do that again.
- **Box has no `shift_jis` codec.** Anything that runs on the box (packers) must be codec-free (raw bytes /
  ASCII / `fon_codec`), never `.encode("shift_jis")`.

## Later ⚪
- **Map** (`MAP01.PVR` / `MAP_CUR.PVR`) — deferred until seen in-game.
