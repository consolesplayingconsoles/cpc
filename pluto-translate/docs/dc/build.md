# Building the patched text binaries — the `packers/` engine

`parsers/` decode a binary FORMAT into translation blocks; **`packers/`** are the
write-side twin: take the original bytes + the translated blocks (the workbench
state.json) and re-emit the binary with the Catalan in place. Config-driven and
format-decoupled, same as the parsers, so it's a reusable engine, not a per-game hack.

```
parsers/ptrtable.py  : parse(data)            packers/ptrtable.py  : pack(orig, blocks, encode, box=None)
parsers/nullsplit.py : parse(data)     →      packers/nullsplit.py : pack(orig, blocks, encode, box, grow)
parsers/lines.py     : parse(data)            packers/lines.py     : (todo, when an INI source needs it)
```

The cardinal trick is the **index rewrite**: Catalan is longer than the Japanese it
replaces, so instead of fragile in-place patching, relocate the text and rewrite the
offset/pointer table. The packer captures format details (record magic, trailers) from
the file, never hardcoding a game's values — the game-specific bits (which files, box
widths, the `encode`/font) are injected.

## One-command build

```
pluto-translate/build-local.sh <game-name> <original-root> <patch-root> [api_base]
```

builds every patched text binary **and** the patched font in one go, e.g.

```
./pluto-translate/build-local.sh "Boku Doraemon (Japan) [ca]" \
    sandbox/boku-doraemon-japan/original sandbox/boku-doraemon-japan/patch
```

Under the hood it runs `dc/build_patch.py` (text) + `dc/fon_codec.py` (font).

**The build reads the LIVE app state from the API — never a file.** `build_patch.py`'s first
arg is a **game name**; it fetches the current state from `api_base` (default
`http://localhost:7700`). Pass an explicit `*.json` path only to build a deliberate snapshot.
Why: a `dist/translations/.../state.json` FILE silently drifted 245 blocks behind the app
(2026-07-01); building it compiled the OLD longer text, so scenes overflowed and translated
lines fell back to Japanese. The API is the single source of truth; the file can lie.

`build_patch.py` reads `sources.config.json`'s `kind` per source, picks the packer, writes every
patched binary (mirroring subdir paths). Boku Doraemon result:

| source | packer | result |
|---|---|---|
| `STORY.PAC` | nullsplit (`grow=False`, box=15) | **3040/7575 lines (≈40%), size kept** — slack ceiling; rest stay JP |
| `DOUGU/ITEMTBL.PAC` | ptrtable | 156 gadget names, size kept |
| `INFO/SECRET.TBL` | ptrtable (box=12) | 8 body-spec hints, size kept (632 B) — spliced in place |

> Confirmed on screen 2026-06-28 (Flycast): the safe build loads and renders Catalan
> dialogue with accents and correct placement. `grow=True` is abandoned (see below).

Encoder is `dc.fon_codec.fw` (full-width + the authored accent glyphs). Accents ride in
Greek-slot codepoints; **the patched `S18RM04.FON` must be in the rebuild** or they show as
Greek letters. Source text must be `fw`-encodable (no `／ ~ % ō` etc. — clean those first).

## ptrtable packer (ITEMTBL, SECRET) — SAFE, proven

`2d f0`-style records behind a u32 pointer table. Rebuild every record with Catalan,
repoint the table, grow or keep-size. Self-round-trips; this is the same logic as the
original itemtbl-expand one-off, generalised. **No runtime risk** — ship it.

## nullsplit packer (STORY.PAC) — SCP/CMD, two modes

STORY.PAC = container of sector-aligned (0x800) `SCP` scenario records → `[ASM][CMD]`
(CMD always last). CMD = `CMD\0` + size + a u32 pointer table → a contiguous, variable-size
command stream; ~1 in 7 commands carry text (`02 ff <spk>` + SJIS). The script addresses
commands **by index through the pointer table** (verified: the apparent internal byte-offset
jumps are all coincidental spans), so growing a text command and bumping the later table
entries preserves control flow. Per scenario we rewrite: the CMD pointer table, the `CMD\0`
size, the SCP section-table CMD size, and rec0's near-end script-length marker (the *only*
internal end-pointer — verified 0 others).

- **`grow=False`** (the only viable mode) — keep each scenario's size constant, greedily fill
  its trailing zero-slack line-by-line. Coverage **≈40%** (3040/7575); lines that do not fit
  stay Japanese. Two things make it work and render correctly:
  - **Clamp.** The `nullsplit` parser over-reads ~4 bytes past a `04ff` page-break into the
    next command's header. The packer clamps each run to its command boundary, so it never
    corrupts the next command. Without the clamp, commands corrupt (a crash cause) and coverage
    collapses to ~1%; with it, ~40%.
  - **Pagination.** `_enc` wraps to **box=15** (native box ~16 wide, 1–2 lines tall) and inserts
    a `04ff` page break every **2 lines**. A single `01ff`-only blob overflows the box and loses
    vertical placement. This mirrors the original expand-line proof, preserving the page skeleton.
- **`grow=True`** — ABANDONED. Scenarios grow and re-concatenate sector-aligned (would give
  100%), but it **CRASHES**: the game locates scenarios by **hardcoded offsets**, not by scanning
  `SCP\0`. Confirmed 2026-06-28 (New Game hangs / black screen). Do not ship it; the mode is kept
  in code only as the round-trip identity check.

### The greedy fill stops early — and "place all" hung the game (2026-07-01)

`grow=False` fills speaker-**turns** in play-order and **stops at the first turn that doesn't fit
the remaining slack**, leaving the rest of the scenario Japanese for a clean unbroken run. Side
effect: a scenario whose Catalan *totals* under slack can still be left partly Japanese, because
some lines are **shorter** than the Japanese (negative expansion) and the prefix fill quits before
reaching them. Scene 41 (the first scene) measures **1298/1388 = fits**, yet the greedy fill lands
only ~46 of 116 turns; the visible Gegant line (block 86) drops to Japanese.

A **"place every line when `sum(expansion) <= slack`"** variant was tried: scene 41 went fully
Catalan (0 unplaced, total 6742→6856/7575) and stayed byte-fit — **but the game then HUNG at the
Take-copter gadget reveal** (`はい タケコプター！`, scene-41 rel 11970). **Reverted to greedy-stop.**

Open question, do not re-attempt place-all without resolving it: the operator had **never reached
that reveal before** (the first-scene fix is what got them there), so it is **not known** whether
the hang is caused by place-all rewriting the tail commands, or is **pre-existing** at that gadget
event in the greedy/original build. Command *movement* (growing a command relocates later ones,
table repointed) was assumed safe, but that rested on the wrong belief that greedy already plays
through scene 41. **Decide it with a hardware/emulator test of the reverted build at the Take-copter
reveal**: if greedy also hangs, the culprit is the gadget-event command around the `rel 11856–11996`
gap (a flash/`道具`-get event the parser may mis-handle), not the fill strategy.

Correctness gates that pass offline: `pack(orig, [], grow=False) == orig` (byte-identical
round-trip); all 76 CMD pointer tables valid + ascending; size kept; greedy slack fill.

## Past the ~30% ceiling — CONDENSE TO FIT (both engine escape hatches are dead)

The slack is ~81 KB; full-fidelity Catalan needs ~310 KB over the Japanese, so only ~30% of
lines fit and that is a HARD floor. Both ways to lift it are **confirmed dead 2026-06-29**:

- **Relocation**: the game finds scenarios by hardcoded offsets (scattered SH4 immediates in
  `1ST_READ.BIN`, no contiguous table, longest run 1–2). The grow build crashes (swirl hang)
  even with a byte-correct splice, so it is the relocation, not the packing.
- **Half-width font**: byte savings would need 1-byte codes to render, but the font is **100%
  full-width** (7808 records, JIS rows 0x21–0x74, zero half-width slots) and the engine draws
  dots for 1-byte codes. Narrower glyphs in full-width slots still cost 2 bytes/char = no saving.

The real lever is **CONDENSE TO FIT**: write tighter Catalan so each scenario's lines fit its
own slack. Bar = **comprehension + a wink at the dub, NOT fidelity** (a non-JP reader gets
nothing from a Japanese line, so a trimmed Catalan one always wins). Optimise per BOX, not per
line; ship alphas. ptrtable (ITEMTBL/SECRET) + textures are SAFE and complete regardless.

## Rebuild + verify

After `build_patch.py`, rebuild the GDI (GDIBuilder "Rebuild Patched GD-ROM", Modified-files
mirroring paths incl. `DOUGU/`, `INFO/`, the patched `.FON`, and the textures) and boot in
Flycast (not OpenEMU). The opening New Year scenario should show Catalan + accents, paginated
2 lines/box. Spot-check a help-Mum / cutscene scenario; a single-scenario glitch would point to
a rec0-marker edge case there.
