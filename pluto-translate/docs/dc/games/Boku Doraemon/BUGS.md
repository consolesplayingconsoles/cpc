# Boku Doraemon (Català) — bug / task tracker

Living list. Status: 🔴 open · 🟡 code changed, NOT yet verified on the console · ✅ confirmed on the DC by the operator · ⚪ later.

## Textures / packing

- 🟡 **Invention/item names overflow one line** — `DOUGU_ITEMTBL.PAC` packs with `box=20`
  (`build_patch.py`), so entries >20 chars wrap to 2 lines. Deployed; awaiting a build to confirm (and
  that no 1-line label wrapped — tune width if so).
- 🟡 **MN mini-game counter** — `ドラやき`→`PASTISSETS`, `ゲット数`→`GUANYATS`. Regenerated, not re-verified.
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
- 🟡 **Menus — pipeline WIRED + draft translations in state, NOT tested.** The menus are font text in
  `.SCP` files (ptrtable format), surfaced as Pluto tabs (`sources.config.json` `*.SCP` force +
  `build_patch` PLAN + `translate.sh` splice). Two now carry byte-fitting drafts in `state.json`
  (test-packed to exactly the original size, `box=None` total-redistribution):
- 🔴 `MAP.SCP` / `NOBIMAP.SCP` — map labels (bonus), not yet drafted.
  Reload Pluto to see the drafts (reconcile overlays them by offset). Terse on purpose — the operator
  will refine within the same budget.
- 🟡 **MN1/MN2/MN3 instruction boxes + timers — DONE, not console-verified.** One script
  `repaint_mn_instr.py` (per-file CONFIG; supersedes the old `repaint_mn2_instr.py`) repaints all three
  `〜そうさ方法〜` boxes → `~ Com es juga ~` + body (A red / B blue, MN3 also Y green), and the
  `残りじかん…秒` timers → `Temps…s`. MN1 also gets its top-left `Ａボタン/Ｂボタン` legend → **Botó A / Botó B**.
  Board text = per-row margin-median green refill; timers/legend on transparent bg = alpha erase. Written
  to the committed `textures/` dir (all three backed up under `.backups/`), sizes unchanged, dorayaki
  counter chunks preserved. Chunk indices differ per file: MN1 box=chunk 2, timer=chunk 5; MN2/MN3 box+timer=chunk 3.
- 🟡 **MN1/MN2/MN3 result + scold bubbles, race flashes, MN3 arrow — DONE, not console-verified.**
  `repaint_mn_dialog.py` (runs after `repaint_mn_instr.py`): 9 Mama speech bubbles (praise ×6 / scold ×3)
  redrawn white next to the kept portraits (`ドラちゃん`→**Doraemon**, `ドラやき`→**pastissets**), auto-fit
  per bubble; the gold race flashes `用意して〜/スタート!!/終了〜!!` → **Llestos… / Ja!! / Fi!!** (vertical
  yellow→orange gradient + dark outline); MN3's `この位置に/かたづけてね` → **Desa-ho / aquí** (gold), red →
  arrow kept. Board text = per-row median-green refill; flashes/arrow = alpha erase. Written to the
  committed `textures/` dir (backed up `.pre-dialog.*`), sizes unchanged, counters + instruction boxes intact.
  → **The whole MN1/2/3 HUD is now Catalan** (counter, instruction box, timer, bubbles, flashes, arrow).
- 🟡 **Main game field HUD (`PARAM.PVM`) — DONE, not console-verified.** `repaint_param.py`: `ドラやき` →
  **`Pastissets`** (green, reduced font to fit its ~76px slot). `月` (pink date suffix) KEPT — no room for a
  Catalan word. `TIME`/digits/icons untouched (only the label's pixels change). PARAM c1-c3 = HUD face
  avatars (no text). New file written to `textures/PARAM.PVM`; auto-spliced by `translate.sh`'s `*.PVM` loop.
- 🔴 **Map + INFO/records screen — deferred.** `MAP01.PVR` / `MAP_CUR.PVR` — do once seen in-game.
  `INFO/JYOU_00.PVR` = the records/status screen (状況: the 3 minigame names 肩たたき/草むしり/おかたづけ,
  せいこう/しっぱい stats, 年/月/週/回/個/点/％ units, じょうほう title) — a separate baked-text screen, still JP.

## Deferred
- Sync confirmed gadget names into `DOUGU/ITEMTBL.PAC` (beta phase).
