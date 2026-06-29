# Translation Pipeline

⚠️ **EXPERIMENTAL & UNDER DEVELOPMENT** — This feature is early-stage. Extraction methods are game-specific and documented per-title. Some consoles have working extractors; others are stubs awaiting community contributions. **Expect broken ROMs, corrupted text, and incomplete extractions.** Test thoroughly before relying on output.

---

A collaborative process for translating Japan-only game ROMs to any language. **Code + docs live together:** each console has `extract.py` (implementation) and `extract.md` (guide), with per-game notes in `games/`.

Your backups, your translations. No API keys required — you bring your own Claude account.

## Directory Structure

```
translation/
  README.md                      # This file
  dc/
    extract.py                   # Dreamcast extraction code
    extract.md                   # Console guide (text encoding, tools, patterns)
    games/
      boku-doraemon.md           # Per-game notes (status, findings, glossary)
  gba/
    extract.md
    games/
      dragon-ball-advanced.md
  megadrive/
    extract.py                   # (in progress)
    extract.md
    games/
      buyuu-retsuden.md
  ws/
    extract.md
```

## Workflow

1. **Choose console** — Find the console dir matching your ROM
2. **Read `extract.md`** — Console-level guide: text encoding, compression, extraction patterns
3. **Read `games/<game>.md`** — Game-specific notes: current extraction status, findings, blockers
4. **Contribute** — Add findings to the `.md` file. If you discover offsets, compression format, or text samples, update the game notes
5. **Extract** — Run the extractor (or follow the guide for manual extraction)
6. **Translate** — Use the glossary and notes provided
7. **Patch** — Follow the reinsertion guide in `extract.md`

## Reuse Strategy: Same Franchise, Same Developer

**Key insight:** Games from the same franchise or developer often share:
- **Glossaries** (character names, items, locations stay consistent)
- **Extraction patterns** (same text encoding, compression, storage layout)
- **Translation notes** (tone, era, cultural context carry over)

**Example:** All Dragon Ball games use the same character names and item names. Build ONE glossary, reuse it across Dragon Ball Z (Mega Drive), Dragon Ball Advance (GBA), etc. The first game's extraction teaches you patterns for the next.

**Action:** When starting a new game, check `games/` for games from the same franchise or publisher. Copy their glossary, reuse their extraction patterns.

## Glossary Format

Create one glossary per franchise. Include:

```markdown
| JP | Romaji | EN | CA (or target) |
|---|---|---|---|
| ドラえもん | Doraemon | Doraemon | Doraemon |
| ドラやき | Dorayaki | Dorayaki | dorayaki |
| タイムマシン | Time Machine | Time Machine | màquina del temps |
```

**Lock proper nouns, character names, item names** — these are untouchable in translation.

**Specify source:** which dub era, which regional release you're matching.

## Extraction Status Format

Document findings as you discover them:

```markdown
## Findings
- **Compression**: LZ77 (20k+ signatures at offset 0x000222+)
- **Pointer table**: Candidates at 0x000008 (need manual inspection)
- **Text encoding**: Shift-JIS, null-terminated
- **Blocks**: XX extracted, YY missing (blocking reason)

## Next Steps
- [ ] Locate actual pointer table
- [ ] Test decompression on first block
- [ ] Cross-reference JP ↔ FR versions
```

## Contribution Guidelines

- **Add findings incrementally**: each discovery goes in `extract.md` or game notes
- **Link to community resources**: if you find a fan translation thread, ROM hacking guide, or existing tool, link it
- **Test as you go**: extract → verify in emulator → document → next step
- **Reuse across franchise**: glossaries and extraction patterns save half the work on the next game

## Community Resources & Tooling

Decades of reusable Dreamcast fan-translation tooling already exists — pull from it before reinventing. All of these are public GitHub/web; only the forum index is Cloudflare-gated (open it in a real browser).

**Index:** [Dreamcast Games Translation Megathread](https://dreamcast-talk.com/forum/viewtopic.php?t=13952) — ~100 DC translations and the tools behind them.

**Reusable tooling:**
- **Derek Pascarella ("ateam")** — the most prolific DC translator; a wall of `github.com/DerekPascarella/<Game>EnglishPatchDreamcast` repos carrying reusable **pointer-table rewriting, font handling, and headless GDI rebuild** patterns. First stop for dialogue-patcher / pointer technique.
- **[derplayer/PDN-FileTypePVR](https://github.com/derplayer/PDN-FileTypePVR)** — Paint.NET plugin to edit PVR textures (the menu/title art).
- **Rolly's tool collection** — http://sega.c0.pl/romhacking_mods_translation.html
- **[XadPT — Boku Doraemon EN-TL](https://dreamcast-talk.com/forum/viewtopic.php?f=52&t=14037)** — the in-progress English translation of our pilot game; complementary effort that hit the same font wall.

**The font wall (every DC translation hits it):** the half-width / accented-glyph problem stalled even SEGAGAGA. For Dreamcast's `S18RM04.FON` we cracked the format (2bpp bitmap, 106-byte records, byte-swapped JIS code, 20px cells) — codec + accent authoring in `dc/fon_codec.py` (its `__main__` regenerates the patched `.FON`), format notes in `dc/extract.md`.
</content>
</invoke>