# Boku Doraemon (Català) — bug / task tracker

Living list. Status: 🔴 open · 🟡 code changed, NOT yet verified on the console · ✅ confirmed on the DC by the operator · ⚪ later.

## QA play-test (DC, 2026-07-03)

**Confirmed working on hardware ✅:** invention/item name 2-line wrap; the whole **MN1/2/3 minigame HUD**
(counter, instruction boxes, timers, bubbles, flashes) — "look amazing"; the **pause/main menu**; the
**field HUD** (`Pastissets` + month counter); dialogue renders (accents/contractions, e.g. `ets un cas…
o estudiar`, `Pa de la memòria`).

**New findings (still JP / broken) 🔴:**
- **Map location labels still JP** — `ジャイアンの家` (Giant's house) etc. Space seen in-game = the bottom
  label bar, **one line, ~full width** (generous). Targets: `MAP.SCP` / `NOBIMAP.SCP` (font labels) and the
  `MAP01.PVR` art. Now unblocked (operator has seen the space).
- **Pocket ("Butxaca") item menu — control legend JP** — the grid screen's controls `いどう / けってい /
  もどる / ページ前 / ページ次` (move / confirm / back / page prev / page next) still Japanese. A separate
  menu screen (not DEFMENU); locate its `.SCP`/table. Item tiles show `?` = unrevealed, NOT a bug.
- **Info / records screen (`じょうほう`) still JP** — confirmed in-game: the 3 minigame names, せいこう/しっぱい
  stats, 年/月/週/回/個/点 units, gadget tallies. `INFO/JYOU_00.PVR` baked-text screen (was deferred).
- **Day-start "第X週" (week N) still JP** — the `4月第4週` transition: `月` kept but `第４週` (week 4) untranslated.
  Find its texture/font ("設4週"-style neon-green screen).
- **Some gadget names show BLANK** — in the gadget-select carousel some objects have an empty name bar,
  others render fine (`Pa de la memòria` = アンキパン). Missing/empty `ITEMTBL` names for some entries →
  finish translating gadget names AND make untranslated ones fall back to JP, not blank. (Ties into the
  deferred "sync gadget names into `DOUGU/ITEMTBL.PAC`".)
- **Choice/selection menu breaks on multiline** — a yes/no-style choice renders garbled when the text
  wraps: `Te'l faré menjar` then a broken `sí … o` split across lines. The multiline choice layout isn't
  handled — the choice-menu format needs single-line packing or a proper 2-line wrap. **Highest-impact bug.**

## Textures / packing

- ✅ **Invention/item name 2-line wrap** — `DOUGU_ITEMTBL.PAC` `box=20`. Confirmed clean on DC 2026-07-03.
- ✅ **MN mini-game counter** — `ドラやき`→`PASTISSETS`, `ゲット数`→`GUANYATS`. Confirmed on DC 2026-07-03.
- 🟡 **Save + sleep prompts — WIRED + drafted in state, NOT built/tested.** Font text (not a texture)
  in `1ST_READ.BIN` (boot exe): two `XX f0 <len>` records sharing the `Ａボタン（はい）／Ｂボタン（いいえ）`
  layout — `ここで　セーブしますか？` (save, @0x03B40C) and `もうおやすみしますか？` (sleep, @0x03B3B4). Now a
  full pipeline source: new `exemsg` parser (`parsers/exemsg.py`, splits each record into Shift-JIS
  text RUNS keyed by absolute offset, keeps `01ff/04ff/05ff` control tokens) + same-size in-place
  packer (`packers/exemsg.py`, pads to exact original length so the exe never changes size), config
  `system` kind, `build_patch` PLAN, `translate.sh` splice, tab label. Catalan in `state.json`:
  save `Desar aquí?`, sleep `Dormir ara?`, buttons `A (Sí)` / `B (No)` — every run within its per-run
  budget; `build_patch` dry-run packs 978148→978148 B, only the 2 regions change. `DPETC/MESSAGE.INI`
  copy stays OFF-LIMITS.
  - ⚠️ UNVERIFIED: whether `1ST_READ.BIN` lives in the spliced `track05` — if it's in another track,
    `inplace.py` prints `(skipped 1ST_READ.BIN)` and the patch won't apply. The box build reports it.
- ✅ **Pause / main menu (`DEFMENU.SCP` / `MAINMENU.SCP`) — confirmed on DC 2026-07-03.** Font text in
  `.SCP` files (ptrtable), surfaced as Pluto tabs; byte-fitting Catalan in `state.json` (`box=None`).
  NOTE: the **Pocket item menu** is a DIFFERENT screen and its control legend is still JP — see QA findings.
- 🔴 `MAP.SCP` / `NOBIMAP.SCP` — map location labels, not yet drafted (now unblocked, see QA findings).
- ✅ **MN1/MN2/MN3 instruction boxes + timers — confirmed on DC 2026-07-03 ("look amazing").** One script
  `repaint_mn_instr.py` (per-file CONFIG; supersedes the old `repaint_mn2_instr.py`) repaints all three
  `〜そうさ方法〜` boxes → `~ Com es juga ~` + body (A red / B blue, MN3 also Y green), and the
  `残りじかん…秒` timers → `Temps…s`. MN1 also gets its top-left `Ａボタン/Ｂボタン` legend → **Botó A / Botó B**.
  Board text = per-row margin-median green refill; timers/legend on transparent bg = alpha erase. Written
  to the committed `textures/` dir (all three backed up under `.backups/`), sizes unchanged, dorayaki
  counter chunks preserved. Chunk indices differ per file: MN1 box=chunk 2, timer=chunk 5; MN2/MN3 box+timer=chunk 3.
- ✅ **MN1/MN2/MN3 result + scold bubbles, race flashes, MN3 arrow — confirmed on DC 2026-07-03.**
  `repaint_mn_dialog.py` (runs after `repaint_mn_instr.py`): 9 Mama speech bubbles (praise ×6 / scold ×3)
  redrawn white next to the kept portraits (`ドラちゃん`→**Doraemon**, `ドラやき`→**pastissets**), auto-fit
  per bubble; the gold race flashes `用意して〜/スタート!!/終了〜!!` → **Llestos… / Ja!! / Fi!!** (vertical
  yellow→orange gradient + dark outline); MN3's `この位置に/かたづけてね` → **Desa-ho / aquí** (gold), red →
  arrow kept. Board text = per-row median-green refill; flashes/arrow = alpha erase. Written to the
  committed `textures/` dir (backed up `.pre-dialog.*`), sizes unchanged, counters + instruction boxes intact.
  → **The whole MN1/2/3 HUD is now Catalan** (counter, instruction box, timer, bubbles, flashes, arrow).
- ✅ **Main game field HUD (`PARAM.PVM`) — confirmed on DC 2026-07-03 ("hud looks good").** `repaint_param.py`:
  `ドラやき` → **`Pastissets`** (green, reduced font to fit its ~76px slot). `月` (pink date suffix) KEPT — no room for a
  Catalan word. `TIME`/digits/icons untouched (only the label's pixels change). PARAM c1-c3 = HUD face
  avatars (no text). New file written to `textures/PARAM.PVM`; auto-spliced by `translate.sh`'s `*.PVM` loop.
- 🔴 **Map, pocket menu, info screen, week-N screen, blank gadget names, multiline choice menu** — all now
  confirmed in-game; details + targets in the **QA play-test** section at the top. Files in play: `MAP.SCP` /
  `NOBIMAP.SCP` / `MAP01.PVR` (map), the pocket-menu `.SCP` (controls), `INFO/JYOU_00.PVR` (records),
  `DOUGU/ITEMTBL.PAC` (gadget names), and the choice-menu packer (multiline break).

## Deferred
- Sync confirmed gadget names into `DOUGU/ITEMTBL.PAC` (beta phase).
