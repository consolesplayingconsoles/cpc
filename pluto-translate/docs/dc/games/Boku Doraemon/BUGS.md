# Boku Doraemon (Català) — bug / task tracker

Status: 🔴 open · 🟡 code/asset done, NOT verified in-game · 🟢 verified in-game · ⚪ later.

## Done this session (2026-07-03), pending a build + in-game check

## Pending

### Choice/selection menu breaks on multiline — 🔴
A yes/no choice renders garbled when the text wraps: `Te'l faré menjar` then a broken `sí … o` split
across lines. Locate the choice/prompt format (STORY.PAC control codes vs a separate table) and
either pack it single-line or lay out 2 lines properly.

### Ela geminada `l·l` — 🟡 code done
Middot glyph authored (4×3 centred dot in Greek slot 0x83CA), mapped in `_ACCENTS`, `fw()` no longer
strips. Build patched font and verify `col·lecció` renders with a visible middot in-game.

## Later ⚪
- **Info screen gadget rows** — `ドラやき`/`タケコプター`/`どこでもドア` counts on the records screen may pull
  from a source separate from the (already-deployed) inventory; check in-game whether they're Catalan.
- **Map** (`MAP01.PVR` / `MAP_CUR.PVR`) — deferred until seen in-game.
