# Boku Doraemon (Català) — bug / task tracker

Status: 🔴 open · 🟡 code/asset done, NOT verified in-game · 🟢 verified in-game · ⚪ later.

## Done this session (2026-07-03), pending a build + in-game check

## Done 2026-07-05, pending in-game check
- **Pocket page part labels** (`INFO/HIDORA_02.PVR`) — 🟡 the eight body-part labels
  (赤外線アイ … あし) → **Ulls infrarojos / Supernas / Bigotis radar / Campaneta gatera / Mans ventosa /
  Butxaca màgica / Cua interruptor / Peus flotants**, repainted in place via `repaint_hidora.py`,
  committed to the textures dir. An earlier session had claimed the "pocket page" done but had only
  repainted `CONT_0.PVR` (the Moure/Tria/Enrere control legend), leaving these labels Japanese.
- **Pocket page transport labels** (`INFO/HIDORA_01.PVR`) — 🟡 the two cyan labels
  `タケコプター` / `どこでもドア` → **Casquet volador / Porta màgica**, repainted via `repaint_hidora01.py`
  (the 8 empty name-slot frames + red magnifier icons are not text; left untouched). Committed to the
  textures dir.
- **`INFO/SECRET.TBL` body-spec hints never reached the disc** — 🟡 the 8 part-description hints
  (all translated in `state.json`) render Japanese in-game because `translate.sh`'s splice list omitted
  `INFO/SECRET.TBL` on a stale "it grows" assumption. It now packs **same-size (632 B)** since the hints
  were condensed, so `inplace.py` splices it fine. Added `INFO/SECRET.TBL` to the splice loop. Rebuild
  to verify in-game.

## Pending

### Choice/selection menu breaks on multiline — 🔴
A multiple choice renders garbled when the text wraps: `Te'l faré menjar` then a broken `sí … o` split
across lines. Locate the choice/prompt format (STORY.PAC control codes vs a separate table) and
either pack it single-line or lay out 2 lines properly.

### Ela geminada `l·l` — 🟡 code done
Middot glyph authored (4×3 centred dot in Greek slot 0x83CA), mapped in `_ACCENTS`, `fw()` no longer
strips. Build patched font and verify `col·lecció` renders with a visible middot in-game.

## Later ⚪
- **Info screen gadget rows** — `ドラやき`/`タケコプター`/`どこでもドア` counts on the records screen may pull
  from a source separate from the (already-deployed) inventory; check in-game whether they're Catalan.
- **Map** (`MAP01.PVR` / `MAP_CUR.PVR`) — deferred until seen in-game.
